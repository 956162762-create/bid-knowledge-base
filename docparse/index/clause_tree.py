"""
条款树 — 条款节点的 SQLite 持久化与查询
"""
import json
import sqlite3
from typing import List, Optional
from ..parser.clause_extractor import ClauseNode


class ClauseTree:
    """条款树存储与查询"""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def _dict(row) -> dict:
        """sqlite3.Row → dict"""
        return {k: row[k] for k in row.keys()} if row else {}

    def insert_all(self, nodes: List[ClauseNode]) -> int:
        """批量插入条款节点"""
        rows = []
        for node in nodes:
            rows.append((
                node.id, node.parent_id, node.node_type,
                node.number, node.title, node.content,
                node.level, node.page_start, node.path,
                1 if node.is_red else 0,
                json.dumps(node.metadata, ensure_ascii=False),
            ))

        self.conn.executemany(
            """INSERT OR REPLACE INTO clause_nodes
               (id, parent_id, node_type, number, title, content,
                level, page_start, path, is_red, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def get_by_number(self, number: str) -> Optional[dict]:
        """通过条款号获取节点"""
        # 尝试多种格式
        variants = [number]
        if number.startswith("§"):
            variants.append(number[1:])       # "§6.1.16" → "6.1.16"
        else:
            variants.append(f"§{number}")     # "6.1.16" → "§6.1.16"

        for v in variants:
            row = self.conn.execute(
                "SELECT * FROM clause_nodes WHERE number = ?", (v,)
            ).fetchone()
            if row:
                return self._dict(row)
        return None

    def get_by_path(self, path: str) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM clause_nodes WHERE path LIKE ? ORDER BY level",
            (f"%{path}%",)
        ).fetchall()
        return [self._dict(r) for r in rows]

    def get_children(self, parent_id: int) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM clause_nodes WHERE parent_id = ? ORDER BY id",
            (parent_id,)
        ).fetchall()
        return [self._dict(r) for r in rows]

    def get_tree(self, root_number: str) -> List[dict]:
        root = self.get_by_number(root_number)
        if not root:
            return []
        result = [root]
        self._collect_children(root["id"], result)
        return result

    def _collect_children(self, parent_id: int, result: List[dict]):
        children = self.get_children(parent_id)
        result.extend(children)
        for child in children:
            self._collect_children(child["id"], result)

    def search_by_keyword(self, keyword: str, limit: int = 20) -> List[dict]:
        rows = self.conn.execute(
            """SELECT * FROM clause_nodes
               WHERE title LIKE ? OR content LIKE ?
               ORDER BY level LIMIT ?""",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [self._dict(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM clause_nodes").fetchone()[0]
