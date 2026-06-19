"""
条款号 O(1) 哈希索引 — 内存 dict + SQLite 持久化

查询路径: dict["§6.1.16"] → (entity_type, entity_id) → 拿条款或表格
"""
import sqlite3
from typing import Optional, Tuple


class ClauseNumberIndex:
    """条款号 → 实体 ID 的 O(1) 映射"""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self._index = {}  # {"§6.1.16": ("clause", 123), "A-8": ("table", 456)}
        self._load_from_db()

    def _load_from_db(self):
        """从持久化表加载到内存"""
        rows = self.conn.execute(
            "SELECT number, entity_type, entity_id FROM clause_number_index"
        ).fetchall()
        for number, entity_type, entity_id in rows:
            self._index[number] = (entity_type, entity_id)

    def _normalize(self, number: str) -> str:
        """标准化条款号"""
        number = number.strip()
        if not number.startswith("§") and not number.startswith("第"):
            # 如果看起来像数字编号
            parts = number.split(".")
            if len(parts) >= 2 and all(p.replace("-", "").replace("_", "").isalnum() for p in parts):
                number = f"§{number}"
        return number

    def get(self, number: str) -> Optional[Tuple[str, int]]:
        """O(1) 查找。返回 (entity_type, entity_id) 或 None"""
        # 精确匹配
        result = self._index.get(number)
        if result:
            return result
        # 尝试标准化
        normalized = self._normalize(number)
        if normalized != number:
            result = self._index.get(normalized)
            if result:
                return result
        # 尝试去 § 前缀
        if number.startswith("§"):
            return self._index.get(number[1:])
        return None

    def register(self, number: str, entity_type: str, entity_id: int):
        """注册新的条款号映射"""
        normalized = self._normalize(number)
        # 注册原格式和标准化格式
        for key in {number, normalized, normalized.lstrip("§"), f"§{number.lstrip('§')}"}:
            if key:
                self._index[key] = (entity_type, entity_id)

        self.conn.execute(
            "INSERT OR REPLACE INTO clause_number_index VALUES (?, ?, ?, datetime('now'))",
            (normalized, entity_type, entity_id),
        )
        self.conn.commit()

    def register_clauses(self, clause_nodes: list):
        """批量注册条款"""
        for node in clause_nodes:
            if node.number:
                self.register(node.number, "clause", node.id)

    def register_tables(self, tables: list):
        """批量注册表格"""
        for table in tables:
            if table.table_number:
                self.register(table.table_number, "table", table.id)

    def __contains__(self, number: str) -> bool:
        return self.get(number) is not None

    def __len__(self) -> int:
        return len(self._index)
