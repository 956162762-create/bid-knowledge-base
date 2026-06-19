"""
项目服务 — 项目生命周期管理 + 结构分析
"""
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict

# 确保 rag_system 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.project_repo import ProjectRepo


class ProjectService:
    """项目生命周期管理"""

    def __init__(self, system_db_path: str, data_root: str):
        self.repo = ProjectRepo(system_db_path, data_root)
        self.data_root = data_root
        self._loaded_engines = {}  # project_id → StructuredEngine

    def create(self, name: str, description: str = "") -> str:
        """创建项目，返回 project_id"""
        return self.repo.create(name, description)

    def list_all(self) -> List[dict]:
        """列出所有项目"""
        return self.repo.list_all()

    def get_info(self, project_id: str) -> Optional[dict]:
        """获取项目信息"""
        project = self.repo.get(project_id)
        if not project:
            return None
        paths = self.repo.get_project_paths(project_id)

        # 读取 struct.db 统计
        clause_count = 0
        table_count = 0
        try:
            import sqlite3
            struct_conn = sqlite3.connect(paths["struct_db"])
            struct_conn.row_factory = sqlite3.Row
            clause_count = struct_conn.execute(
                "SELECT COUNT(*) FROM clause_nodes"
            ).fetchone()[0]
            table_count = struct_conn.execute(
                "SELECT COUNT(*) FROM tables"
            ).fetchone()[0]
            struct_conn.close()
        except Exception:
            pass

        return {
            "id": project_id,
            "name": project["name"],
            "description": project.get("description", ""),
            "created_at": project.get("created_at", ""),
            "clause_count": clause_count,
            "table_count": table_count,
            "paths": paths,
        }

    def analyze(self, project_id: str) -> Optional[dict]:
        """分析项目文档（从 struct.db 读取已有分析结果）"""
        paths = self.repo.get_project_paths(project_id)
        if not paths:
            return None

        try:
            from docparse.builder import StructuredEngine
            engine = StructuredEngine(paths["struct_db"])
            return {
                "project_id": project_id,
                "clause_count": engine.clause_count,
                "table_count": engine.table_count,
                "index_size": len(engine.number_index),
                "status": "ready" if engine.is_built else "pending",
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def ingest_document(self, project_id: str, file_path: str) -> dict:
        """
        摄入文档到项目：结构化解析 + 向量化叙述性段落

        1. 调用 docparse 构建条款树 + 表格库
        2. 提取叙述性段落 → 向量切片入 ChromaDB
        3. 更新文档状态
        """
        paths = self.repo.get_project_paths(project_id)
        if not paths:
            raise ValueError(f"Project {project_id} not found")

        # Step 1: 结构化解析
        from docparse.builder import StructuredEngine
        engine = StructuredEngine(paths["struct_db"])
        result = engine.build(file_path)

        # Step 2: 记录文档元数据到 project.db
        import sqlite3
        meta_conn = sqlite3.connect(paths["meta_db"])
        meta_conn.row_factory = sqlite3.Row
        meta_conn.execute(
            """INSERT INTO documents
               (file_name, file_path, status, clause_count, table_count, parsed_at)
               VALUES (?, ?, 'ready', ?, ?, datetime('now'))""",
            (os.path.basename(file_path), file_path,
             result["clause_count"], result["table_count"]),
        )
        meta_conn.commit()
        doc_id = meta_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        meta_conn.close()

        # Step 3: 向量化叙述性段落（后续可选，Phase 1 先跳过）
        # vectorize_narrative_chunks(project_id, file_path)

        return {
            "document_id": doc_id,
            "file_name": os.path.basename(file_path),
            "clause_count": result["clause_count"],
            "table_count": result["table_count"],
            "index_size": result["index_size"],
            "status": "ready",
        }

    def delete_project(self, project_id: str) -> bool:
        return self.repo.delete(project_id)
