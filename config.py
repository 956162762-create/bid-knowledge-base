"""
RAG 系统配置模块 - 所有可调参数集中管理

支持两种嵌入方案:
  - gemini:  Google Gemini API (推荐, 无需下载模型)
  - local:   本地 sentence-transformers (需下载模型, 不依赖外部API)
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RAGConfig:
    """RAG 系统的完整配置"""

    # ===== 文档处理 =====
    chunk_strategy: str = "paragraph"   # "paragraph" | "fixed_size"
    chunk_size: int = 500               # 固定大小分块时每块的最大字符数
    chunk_overlap: int = 50             # 块之间的重叠字符数

    # ===== 嵌入模型 =====
    # 提供者: "gemini" (API) 或 "local" (sentence-transformers)
    embedding_provider: str = "local"
    # Gemini 嵌入模型
    gemini_embedding_model: str = "text-embedding-004"
    # 本地嵌入模型路径或 HuggingFace ID
    local_embedding_model: str = "./models/bge-small-zh-v1.5"
    # 嵌入向量维度和归一化
    embedding_dimension: int = 768
    normalize_embeddings: bool = True

    # ===== 向量数据库 =====
    chroma_persist_dir: Optional[str] = "./chroma_db"
    chroma_collection_name: str = "rag_documents"

    # ===== 检索 =====
    retrieval_top_k: int = 5
    rerank_top_k: int = 3

    # ===== 重排序 =====
    # 提供者: "gemini" | "local" | "none"
    rerank_provider: str = "local"
    # 本地 CrossEncoder 模型路径或 HuggingFace ID
    local_rerank_model: str = "./models/mmarco-mMiniLMv2-L12-H384-v1"

    # ===== LLM 生成 =====
    llm_model: str = "gemini-2.5-flash"
    temperature: float = 0.3
    max_output_tokens: int = 1024

    # ===== API 密钥 =====
    google_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY")
    )


default_config = RAGConfig()
