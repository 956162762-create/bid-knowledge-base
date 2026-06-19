"""
规则引擎 — 三处管道钩子 + 规则匹配

钩子位置:
  pre-retrieval   → 修改搜索策略
  post-retrieval  → 过滤/增强检索结果
  post-generation → 格式化答案

规则存储: project.db → rules 表
支持类型: source_label, checkbox_format, include_always, return_table, return_clause, custom
"""
import json
import re
import sqlite3
from typing import List, Dict, Optional, Any


class RulesEngine:
    """规则匹配与应用"""

    def __init__(self, meta_db_path: str):
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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_entry_id INTEGER,
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
        self.conn.commit()

    # ── 规则 CRUD ──

    def add_rule(self, name: str, rule_type: str, condition: dict,
                 action: dict, priority: int = 0, description: str = "") -> int:
        """添加规则，返回 rule_id"""
        cursor = self.conn.execute(
            """INSERT INTO rules (name, rule_type, condition_json, action_json, priority, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, rule_type, json.dumps(condition, ensure_ascii=False),
             json.dumps(action, ensure_ascii=False), priority, description),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_rules(self, enabled_only: bool = True) -> List[dict]:
        """列出所有规则"""
        sql = "SELECT * FROM rules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY priority DESC"
        rows = self.conn.execute(sql).fetchall()
        return [self._unpack(r) for r in rows]

    def toggle_rule(self, rule_id: int, enabled: bool):
        self.conn.execute("UPDATE rules SET enabled = ? WHERE id = ?",
                          (1 if enabled else 0, rule_id))
        self.conn.commit()

    # ── 规则匹配 ──

    def match(self, query: str, context: dict = None) -> List[dict]:
        """匹配当前查询应触发的所有规则"""
        rules = self.list_rules(enabled_only=True)
        matched = []

        for rule in rules:
            condition = rule.get("condition", {})
            keywords = condition.get("keywords", [])

            if not keywords:
                continue

            # 关键词匹配
            query_lower = query.lower()
            hits = sum(1 for kw in keywords if kw.lower() in query_lower)
            if hits > 0:
                rule["_match_score"] = hits / len(keywords)
                matched.append(rule)

        matched.sort(key=lambda r: r["_match_score"], reverse=True)
        return matched

    # ── 三处钩子 ──

    def apply_pre_retrieval(self, query: str, context: dict = None) -> dict:
        """
        pre-retrieval 钩子: 修改搜索策略

        Returns: {"modified_query": str, "additional_searches": List[str]}
        """
        rules = self.match(query, context)
        additional_searches = []

        for rule in rules:
            action = rule.get("action", {})
            if rule.get("rule_type") in ("include_always", "return_table"):
                additional_searches.extend(
                    action.get("additional_search_queries", [])
                )
            if action.get("table_numbers"):
                additional_searches.extend(action["table_numbers"])

        return {
            "modified_query": query,
            "additional_searches": list(set(additional_searches)),
            "triggered_rules": [r["name"] for r in rules],
        }

    def apply_post_generation(self, query: str, answer: str,
                              context: dict = None) -> str:
        """
        post-generation 钩子: 格式化答案

        应用: source_label, checkbox_format（checkbox 检查答案内容，非查询）
        """
        rules = self.match(query, context)
        # 勾选框格式化始终应用（不依赖查询匹配）
        all_rules = self.list_rules(enabled_only=True)
        checkbox_rules = [r for r in all_rules
                         if r["rule_type"] == "checkbox_format" and r not in rules]
        rules = rules + checkbox_rules

        modified = answer

        for rule in rules:
            action = rule.get("action", {})
            rule_type = rule.get("rule_type", "")

            # 来源标注
            if rule_type == "source_label":
                label = action.get("label_template", "")
                sources = action.get("sources", [])
                if sources and label:
                    modified += f"\n\n---\n*{label}: {', '.join(sources)}*"

            # 勾选框格式统一（始终应用，不依赖查询匹配）
            if rule_type == "checkbox_format":
                modified = modified.replace("[x]", "[✓]")
                modified = modified.replace("[X]", "[✓]")
                modified = modified.replace("☑", "[✓]")
                modified = modified.replace("□", "[ ]")

        return modified

    # ── 预置规则（YAML 导入/导出）─

    def seed_preset_rules(self):
        """初始化预置规则（首次使用时调用）"""
        presets = [
            {
                "name": "合同文件来源标注",
                "rule_type": "source_label",
                "condition": {"keywords": ["§6", "合同", "条款", "安全管理"]},
                "action": {
                    "label_template": "来自合同文件",
                    "sources": ["合同条件 §6.x"],
                },
                "description": "当查询涉及合同文件内容时，标注来源",
            },
            {
                "name": "勾选框格式统一",
                "rule_type": "checkbox_format",
                "condition": {"keywords": ["[x]", "[X]", "☑", "□"]},
                "action": {
                    "replace_map": {"[x]": "[✓]", "[X]": "[✓]", "☑": "[✓]", "□": "[ ]"},
                },
                "description": "统一勾选框符号为 [✓] / [ ]",
            },
            {
                "name": "危大工程-A8优先",
                "rule_type": "return_table",
                "condition": {"keywords": ["危大工程", "危险性较大", "重大危险源"]},
                "action": {
                    "table_numbers": ["A-8"],
                    "additional_search_queries": ["A-8", "§6.1.16"],
                },
                "description": "查询危大工程时自动返回 A-8 清单",
            },
        ]

        for preset in presets:
            existing = self.conn.execute(
                "SELECT id FROM rules WHERE name = ?", (preset["name"],)
            ).fetchone()
            if not existing:
                self.add_rule(**preset)

    # ── YAML 导入/导出 ──

    def export_yaml(self) -> str:
        """导出规则为 YAML 字符串"""
        import yaml
        rules = self.list_rules(enabled_only=False)
        export = []
        for r in rules:
            export.append({
                "name": r["name"],
                "rule_type": r["rule_type"],
                "condition": r.get("condition", {}),
                "action": r.get("action", {}),
                "priority": r["priority"],
                "enabled": bool(r["enabled"]),
                "description": r.get("description", ""),
            })
        return yaml.dump(export, allow_unicode=True, default_flow_style=False)

    def import_yaml(self, yaml_str: str) -> int:
        """从 YAML 导入规则，返回导入数量"""
        import yaml
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, list):
            data = [data]
        count = 0
        for item in data:
            # 检查是否已存在同名规则
            existing = self.conn.execute(
                "SELECT id FROM rules WHERE name = ?", (item["name"],)
            ).fetchone()
            if existing:
                continue  # 跳过重复
            self.add_rule(
                name=item["name"],
                rule_type=item["rule_type"],
                condition=item.get("condition", {}),
                action=item.get("action", {}),
                priority=item.get("priority", 0),
                description=item.get("description", ""),
            )
            count += 1
        return count

    def _unpack(self, row) -> dict:
        d = {k: row[k] for k in row.keys()}
        for field in ["condition_json", "action_json"]:
            if field in d:
                key = field.replace("_json", "")
                try:
                    d[key] = json.loads(d.pop(field))
                except (json.JSONDecodeError, TypeError):
                    d[key] = {}
        if "condition" not in d:
            d["condition"] = {}
        if "action" not in d:
            d["action"] = {}
        return d
