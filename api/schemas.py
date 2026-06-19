"""
Pydantic 请求/响应模型
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectInfo(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    document_count: int = 0


class IngestResult(BaseModel):
    document_id: int
    file_name: str
    clause_count: int
    table_count: int
    index_size: int
    status: str


class QueryRequest(BaseModel):
    question: str
    stream: bool = False
    use_agent: bool = False


class SourceRef(BaseModel):
    clause_number: Optional[str] = None
    table_number: Optional[str] = None
    title: str = ""
    path: str = ""
    content_preview: str = ""


class QueryResponse(BaseModel):
    answer: str
    intent: str = ""
    path: str = ""                      # "structured" | "semantic"
    sources: List[SourceRef] = []
    applied_rules: List[str] = []


class TemplateMatch(BaseModel):
    template_name: str
    match_reason: str
    required: bool = False


class TemplateMatchResponse(BaseModel):
    templates: List[TemplateMatch]


class ExportRequest(BaseModel):
    sections: List[str] = []
    format: str = "docx"


class ExportResponse(BaseModel):
    download_url: str
    file_size: int = 0
