"""
记忆管理器 — 存储/检索/上下文注入

记忆分类:
  - preference: 用户偏好（如"优先用表格形式回答"）
  - correction: 用户纠错（如"暗挖不涉及本项目"）
  - output: 保存的输出（如生成的技术标大纲）
  - note: 通用笔记

自动升级：同类别同 key 的 correction 达到阈值 → 触发 promote_to_rule()
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta


class MemoryManager:
    """记忆存储与检索"""

    PROMOTE_THRESHOLD = 3  # 同类纠错达到 3 次自动转规则

    def __init__(self, meta_db_path: str):
        """meta_db_path: project.db 路径"""
        self.db_path = meta_db_path
        self._conn = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """确保 memory_entries 表存在"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL CHECK(category IN ('preference','correction','output','note')),
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT DEFAULT 'user',
                importance REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_cat_key ON memory_entries(category, key)
        """)
        self.conn.commit()

    # ── 存储 ──

    def store(self, category: str, key: str, value: Any,
              source: str = "user", importance: float = 0.5) -> int:
        """存储一条记忆，返回 entry_id"""
        value_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        cursor = self.conn.execute(
            """INSERT INTO memory_entries (category, key, value, source, importance)
               VALUES (?, ?, ?, ?, ?)""",
            (category, key, value_str, source, importance),
        )
        self.conn.commit()
        return cursor.lastrowid

    def store_correction(self, query: str, original_answer: str,
                         corrected_answer: str, context: dict = None) -> int:
        """便捷方法：存储纠错记忆"""
        key = self._make_correction_key(query)
        value = {
            "query": query,
            "original": original_answer[:500],
            "corrected": corrected_answer[:500],
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
        }
        entry_id = self.store("correction", key, value, importance=0.8)

        # 检查是否需要升级为规则
        count = self._count_similar_corrections(key)
        if count >= self.PROMOTE_THRESHOLD:
            self.promote_to_rule(entry_id)

        return entry_id

    def store_preference(self, key: str, value: Any) -> int:
        """便捷方法：存储偏好"""
        return self.store("preference", key, value)

    def store_output(self, key: str, output_text: str) -> int:
        """便捷方法：存储输出"""
        return self.store("output", key, output_text)

    # ── 检索 ──

    def retrieve(self, category: str = None, key: str = None,
                 limit: int = 10) -> List[dict]:
        """检索记忆（按类别/关键字）"""
        sql = "SELECT * FROM memory_entries WHERE 1=1"
        params = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if key:
            sql += " AND key LIKE ?"
            params.append(f"%{key}%")

        sql += " ORDER BY importance DESC, access_count DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        self._bump_access([r["id"] for r in rows])
        return [self._unpack(r) for r in rows]

    def get_context_for_query(self, query: str) -> List[dict]:
        """获取与查询相关的记忆上下文（注入到 LLM prompt）"""
        # 1. 所有偏好（永久注入）
        preferences = self.retrieve("preference", limit=5)

        # 2. 与查询关键词匹配的纠错
        keywords = self._extract_keywords(query)
        corrections = []
        for kw in keywords:
            corrections.extend(self.retrieve("correction", key=kw, limit=3))

        # 去重
        seen = set()
        context = []
        for item in preferences + corrections:
            if item["id"] not in seen:
                seen.add(item["id"])
                context.append(item)
        return context[:8]

    def get_recent(self, category: str = None, hours: int = 24,
                   limit: int = 10) -> List[dict]:
        """获取最近的记忆"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        sql = "SELECT * FROM memory_entries WHERE created_at >= ?"
        params = [cutoff]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [self._unpack(r) for r in rows]

    # ── 升级为规则 ──

    def promote_to_rule(self, memory_entry_id: int) -> Optional[int]:
        """将记忆升级为永久规则。返回 rule_id 或 None"""
        entry = self.conn.execute(
            "SELECT * FROM memory_entries WHERE id = ?", (memory_entry_id,)
        ).fetchone()
        if not entry:
            return None

        entry = self._unpack(entry)
        # 确保 rules 表存在
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_entry_id INTEGER REFERENCES memory_entries(id),
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                rule_type TEXT NOT NULL DEFAULT 'custom',
                condition_json TEXT NOT NULL DEFAULT '{}',
                action_json TEXT NOT NULL DEFAULT '{}',
                priority INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # 从记忆内容推断规则条件
        value = entry["value"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {"text": value}

        query_text = value.get("query", entry["key"])
        keywords = self._extract_keywords(query_text)
        condition = {"keywords": keywords} if keywords else {}

        action = {
            "corrected_answer": value.get("corrected", ""),
            "note": f"用户纠错（第{self._count_similar_corrections(entry['key'])}次）→ 自动转为规则",
        }

        cursor = self.conn.execute(
            """INSERT INTO rules (memory_entry_id, name, description, rule_type, condition_json, action_json)
               VALUES (?, ?, ?, 'custom', ?, ?)""",
            (
                memory_entry_id,
                f"自动规则: {entry['key'][:60]}",
                f"从记忆 {memory_entry_id} 自动生成",
                json.dumps(condition, ensure_ascii=False),
                json.dumps(action, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ── 辅助方法 ──

    def _make_correction_key(self, query: str) -> str:
        """为纠错生成稳定的 key"""
        return f"corr_{hash(query) % 100000:05d}_{query[:40]}"

    def _count_similar_corrections(self, key: str) -> int:
        """统计相似纠错的数量"""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_entries WHERE category = 'correction' AND key = ?",
            (key,)
        ).fetchone()
        return row["cnt"] if row else 0

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本提取关键词"""
        import re
        clean = re.sub(r'[？?，,。！!、\s]+', ' ', str(text))
        words = [w.strip() for w in clean.split() if len(w.strip()) >= 2]
        return words[:5]

    def _bump_access(self, ids: List[int]):
        """增加访问计数"""
        for mid in ids:
            self.conn.execute(
                "UPDATE memory_entries SET access_count = access_count + 1 WHERE id = ?",
                (mid,)
            )
        self.conn.commit()

    def _unpack(self, row) -> dict:
        d = {k: row[k] for k in row.keys()}
        if "value" in d and isinstance(d["value"], str):
            try:
                d["value"] = json.loads(d["value"])
            except json.JSONDecodeError:
                pass
        return d
