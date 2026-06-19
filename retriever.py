"""
检索器 - 从向量数据库中检索相关文档块
"""
from typing import List
from embedder import Embedder
from vector_store import VectorStore
from config import RAGConfig


class Retriever:
    """语义检索器: 嵌入查询 → 向量搜索 → 返回候选块"""

    def __init__(self, embedder: Embedder, vector_store: VectorStore, config: RAGConfig = None):
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config or RAGConfig()

    def retrieve(self, query: str, top_k: int = None) -> List[dict]:
        """
        检索与查询最相关的文档块

        Args:
            query: 用户查询文本
            top_k: 返回数量 (默认使用配置中的值)

        Returns:
            [{"text": ..., "source": ..., "chunk_id": ..., "distance": ...}, ...]
        """
        if top_k is None:
            top_k = self.config.retrieval_top_k

        # 1. 将查询转为向量
        query_embedding = self.embedder.embed(query)

        # 2. 在向量数据库中搜索
        results = self.vector_store.query(query_embedding, top_k=top_k)

        # 3. 整理返回格式
        retrieved = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                chunk_data = {
                    "text": doc,
                    "source": results["metadatas"][0][i].get("source", ""),
                    "chunk_id": results["metadatas"][0][i].get("chunk_id", ""),
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                }
                retrieved.append(chunk_data)

        return retrieved
