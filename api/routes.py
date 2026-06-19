"""
API 路由定义 — 挂载到 NiceGUI 的 FastAPI app 上

用法: 在 ui/app.py 中调用 register_routes(app) 即可
"""
import os
from typing import Optional
from .schemas import (
    ProjectCreate, ProjectInfo, IngestResult,
    QueryRequest, QueryResponse, SourceRef,
    TemplateMatchResponse, ExportRequest, ExportResponse,
)


class APIRoutes:
    """API 路由集合。Phase 1 提供基本端点，后续 Phase 逐步丰富。"""

    def __init__(self, project_service=None, query_service=None):
        self.project_service = project_service
        self.query_service = query_service

    def register(self, nicegui_app):
        """将所有端点注册到 NiceGUI 的 FastAPI app 上"""
        app = nicegui_app

        @app.api.get("/api/projects")
        async def list_projects():
            """列出所有项目"""
            if not self.project_service:
                return []
            projects = self.project_service.list_all()
            return [
                {"id": p["id"], "name": p["name"],
                 "description": p.get("description", ""),
                 "created_at": p.get("created_at", "")}
                for p in projects
            ]

        @app.api.post("/api/projects")
        async def create_project(body: ProjectCreate):
            """创建新项目"""
            if not self.project_service:
                return {"error": "project_service not initialized"}, 503
            project_id = self.project_service.create(body.name, body.description)
            return {"project_id": project_id}

        @app.api.get("/api/projects/{project_id}")
        async def get_project(project_id: str):
            """获取项目详情"""
            if not self.project_service:
                return {"error": "project_service not initialized"}, 503
            info = self.project_service.get_info(project_id)
            if not info:
                return {"error": "Project not found"}, 404
            return info

        @app.api.post("/api/projects/{project_id}/analyze")
        async def analyze_document(project_id: str):
            """分析已上传的文档（Phase 1 简化版：从 test_struct.db 读取已有结果）"""
            if not self.project_service:
                return {"error": "project_service not initialized"}, 503
            result = self.project_service.analyze(project_id)
            if not result:
                return {"error": "Analysis failed"}, 500
            return result

        @app.api.post("/api/projects/{project_id}/query")
        async def query(project_id: str, body: QueryRequest):
            """智能问答"""
            if not self.query_service:
                return {"error": "query_service not initialized"}, 503
            result = self.query_service.query(project_id, body.question)
            return {
                "answer": result.get("answer", ""),
                "intent": result.get("intent", ""),
                "path": result.get("path", "semantic"),
                "sources": result.get("sources", []),
            }

        @app.api.get("/api/projects/{project_id}/templates/match")
        async def match_templates(project_id: str):
            """匹配适用的技术标模板（Phase 4 实现）"""
            return {"templates": [], "message": "Not implemented yet (Phase 4)"}

        @app.api.post("/api/projects/{project_id}/export")
        async def export_tech_bid(project_id: str, body: ExportRequest):
            """导出技术标（Phase 4 实现）"""
            return {"message": "Not implemented yet (Phase 4)"}

        print("  ✓ API 路由已注册")


# 工厂函数
def create_routes(project_service=None, query_service=None) -> APIRoutes:
    return APIRoutes(project_service, query_service)
