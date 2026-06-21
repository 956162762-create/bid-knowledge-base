"""
项目仓库 — 项目 CRUD + 数据目录管理
"""
import os
import uuid
import sqlite3
from typing import Optional, List, Dict
from pathlib import Path


class ProjectRepo:
    """项目管理持久化"""

    def __init__(self, system_db_path: str, data_root: str):
        """
        Args:
            system_db_path: system.db 路径
            data_root: 数据目录根路径 (data/)
        """
        self.system_db_path = system_db_path
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        # 延迟初始化连接
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            from .schema import init_system_db
            self._conn = init_system_db(self.system_db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def create(self, name: str, description: str = "") -> str:
        """创建新项目，初始化其数据目录和数据库文件。返回 project_id。"""
        project_id = str(uuid.uuid4())[:8]

        # 创建项目目录结构
        project_dir = self.data_root / "projects" / project_id
        struct_db = project_dir / "struct.db"
        chroma_dir = project_dir / "chroma"
        meta_db = project_dir / "project.db"

        project_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir.mkdir(exist_ok=True)

        # 初始化 project.db
        from .schema import init_project_db
        init_project_db(str(meta_db))

        # 注册到 system.db
        self.conn.execute(
            """INSERT INTO projects (id, name, description, struct_db_path, chroma_path, meta_db_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, name, description,
             str(struct_db), str(chroma_dir), str(meta_db)),
        )
        self.conn.commit()
        return project_id

    def get(self, project_id: str) -> Optional[dict]:
        """获取项目信息"""
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return {k: row[k] for k in row.keys()} if row else None

    def list_all(self) -> List[dict]:
        """列出所有项目"""
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def update(self, project_id: str, **kwargs) -> None:
        """更新项目字段"""
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [project_id]
        self.conn.execute(
            f"UPDATE projects SET {sets}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        self.conn.commit()

    def delete(self, project_id: str) -> bool:
        """删除项目及其所有数据文件"""
        project = self.get(project_id)
        if not project:
            return False

        # 删除数据库记录
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

        # 删除文件
        project_dir = self.data_root / "projects" / project_id
        if project_dir.exists():
            import shutil
            shutil.rmtree(str(project_dir))

        return True

    def get_project_paths(self, project_id: str) -> Optional[dict]:
        """获取项目的数据路径"""
        project = self.get(project_id)
        if not project:
            return None
        return {
            "struct_db": project["struct_db_path"],
            "chroma_dir": project["chroma_path"],
            "chroma_path": project["chroma_path"],
            "meta_db": project["meta_db_path"],
            "project_dir": str(self.data_root / "projects" / project_id),
        }
