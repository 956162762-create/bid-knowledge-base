"""
表格库 — 表格的 SQLite 持久化与查询
"""
import json
import sqlite3
from typing import List, Optional
from ..parser.table_extractor import ExtractedTable


class TableStore:
    """表格存储与查询"""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self.conn.row_factory = sqlite3.Row

    def insert_all(self, tables: List[ExtractedTable]) -> int:
        """批量插入表格"""
        rows = []
        for t in tables:
            rows.append((
                t.id, t.table_number, t.title, t.caption,
                t.chapter_ref, t.page_number,
                json.dumps(t.rows, ensure_ascii=False),
                json.dumps(t.checkbox_map, ensure_ascii=False),
                json.dumps(t.merged_cells, ensure_ascii=False),
                t.row_count, t.col_count, t.raw_html,
            ))

        self.conn.executemany(
            """INSERT OR REPLACE INTO tables
               (id, table_number, title, caption, chapter_ref, page_number,
                rows_json, checkbox_json, merged_json, row_count, col_count, raw_html)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def get_by_number(self, number: str) -> Optional[dict]:
        """通过表格编号获取完整表格"""
        row = self.conn.execute(
            "SELECT * FROM tables WHERE table_number = ?", (number,)
        ).fetchone()
        if row:
            d = dict(row)
            d["rows"] = json.loads(d.pop("rows_json", "[]"))
            d["checkbox_map"] = json.loads(d.pop("checkbox_json", "{}"))
            d["merged_cells"] = json.loads(d.pop("merged_json", "[]"))
            return d
        return None

    def get_by_chapter(self, chapter_ref: str) -> List[dict]:
        """获取某章节下的所有表格"""
        rows = self.conn.execute(
            "SELECT * FROM tables WHERE chapter_ref = ?", (chapter_ref,)
        ).fetchall()
        return [self._unpack(row) for row in rows]

    def search_by_title(self, keyword: str, limit: int = 10) -> List[dict]:
        """按表格标题关键词搜索"""
        rows = self.conn.execute(
            "SELECT * FROM tables WHERE title LIKE ? OR table_number LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit),
        ).fetchall()
        return [self._unpack(row) for row in rows]

    def get_all(self) -> List[dict]:
        rows = self.conn.execute("SELECT * FROM tables ORDER BY id").fetchall()
        return [self._unpack(row) for row in rows]

    def _unpack(self, row) -> dict:
        d = {k: row[k] for k in row.keys()}
        d["rows"] = json.loads(d.pop("rows_json", "[]"))
        d["checkbox_map"] = json.loads(d.pop("checkbox_json", "{}"))
        d["merged_cells"] = json.loads(d.pop("merged_json", "[]"))
        return d

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM tables").fetchone()[0]
