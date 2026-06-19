"""
结构化引擎构建器 — 协调解析→提取→索引全流程

用法:
    engine = StructuredEngine("path/to/struct.db")
    engine.build("path/to/bidding_doc.docx")
    clause = engine.get_clause("§6.1.16")
    table = engine.get_table("A-8")
"""
import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from .parser.docx_parser import DocxParser
from .parser.clause_extractor import ClauseExtractor
from .parser.table_extractor import TableExtractor
from .index.clause_tree import ClauseTree
from .index.table_store import TableStore
from .index.clause_number_index import ClauseNumberIndex
from .schema import init_db


class StructuredEngine:
    """结构化引擎 — 对外统一接口"""

    def __init__(self, db_path: str):
        """
        Args:
            db_path: struct.db 路径（不存在则自动创建）
        """
        self.db_path = db_path
        self.conn = init_db(db_path)
        self.conn.row_factory = sqlite3.Row
        self.clause_tree = ClauseTree(self.conn)
        self.table_store = TableStore(self.conn)
        self.number_index = ClauseNumberIndex(self.conn)
        self._built = False

    def build(self, docx_path: str) -> dict:
        """
        构建结构化索引。

        Returns:
            {"clause_count": int, "table_count": int, "index_size": int}
        """
        print(f"解析文档: {docx_path}")

        # Step 1: 解析 docx
        parser = DocxParser(docx_path)
        elements = parser.parse()
        print(f"  · 元素总数: {len(elements)}")

        # Step 2: 提取条款树
        extractor = ClauseExtractor()
        clause_nodes = extractor.extract(elements)
        print(f"  · 条款节点: {len(clause_nodes)}")

        # Step 3: 提取表格
        table_extractor = TableExtractor(clause_nodes)
        tables = table_extractor.extract(elements)
        print(f"  · 表格数量: {len(tables)}")

        # Step 4: 存入 SQLite
        self.clause_tree.insert_all(clause_nodes)
        self.table_store.insert_all(tables)

        # Step 5: 建 O(1) 哈希索引
        self.number_index.register_clauses(clause_nodes)
        self.number_index.register_tables(tables)
        print(f"  · 条款号索引: {len(self.number_index)} 条")

        # Step 6: 记录文档元数据
        self.conn.execute(
            """INSERT INTO document_meta (file_name, file_path, clause_count, table_count)
               VALUES (?, ?, ?, ?)""",
            (os.path.basename(docx_path), docx_path,
             len(clause_nodes), len(tables)),
        )
        self.conn.commit()
        self._built = True

        return {
            "clause_count": len(clause_nodes),
            "table_count": len(tables),
            "index_size": len(self.number_index),
        }

    # ── 查询接口 ──

    def get_clause(self, number: str) -> Optional[dict]:
        """O(1) 通过条款号获取条款"""
        result = self.number_index.get(number)
        if result is None:
            return None
        entity_type, entity_id = result
        if entity_type == "clause":
            return self.clause_tree.get_by_number(number) or \
                   self._get_clause_by_id(entity_id)
        return None

    def _get_clause_by_id(self, clause_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM clause_nodes WHERE id = ?", (clause_id,)
        ).fetchone()
        return {k: row[k] for k in row.keys()} if row else None

    def get_table(self, number: str) -> Optional[dict]:
        """O(1) 通过表格编号获取完整表格"""
        result = self.number_index.get(number)
        if result is None:
            # 回退到标题搜索
            return self.table_store.get_by_number(number)
        entity_type, entity_id = result
        if entity_type == "table":
            # 直接用 ID 查
            row = self.conn.execute(
                "SELECT * FROM tables WHERE id = ?", (entity_id,)
            ).fetchone()
            if row:
                return self.table_store._unpack(row)
        # fallback
        return self.table_store.get_by_number(number)

    def search_clauses(self, keyword: str, limit: int = 20) -> List[dict]:
        """关键词搜索条款"""
        return self.clause_tree.search_by_keyword(keyword, limit)

    def search_tables(self, keyword: str, limit: int = 10) -> List[dict]:
        """关键词搜索表格"""
        return self.table_store.search_by_title(keyword, limit)

    def get_clause_tree(self, root_number: str) -> List[dict]:
        """获取某节点的完整子树"""
        return self.clause_tree.get_tree(root_number)

    @property
    def clause_count(self) -> int:
        return self.clause_tree.count()

    @property
    def table_count(self) -> int:
        return self.table_store.count()

    @property
    def is_built(self) -> bool:
        return self._built or self.clause_count > 0
