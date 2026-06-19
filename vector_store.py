"""
向量存储 - 基于 ChromaDB 的向量数据库封装
"""
import os
from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from config import RAGConfig


class VectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.collection_name = self.config.chroma_collection_name

        # 初始化 ChromaDB 客户端
        persist_dir = self.config.chroma_persist_dir
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
            print(f"使用持久化存储: {persist_dir}")
            self.client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            print("使用临时存储 (重启后数据丢失)")
            self.client = chromadb.EphemeralClient(
                settings=ChromaSettings(anonymized_telemetry=False),
            )

        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # 使用余弦相似度
        )

    def add_chunks(self, chunks: List[dict], embeddings: List[List[float]],
                   batch_size: int = 5000) -> None:
        """
        批量添加文档块及其向量 (自动分批避免超过 ChromaDB 限制)

        Args:
            chunks: [{"text": ..., "source": ..., "chunk_id": ...}, ...]
            embeddings: 对应的向量列表
            batch_size: 每批最大数量 (ChromaDB 默认上限约 5461)
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"块数({len(chunks)})与向量数({len(embeddings)})不匹配")

        total = len(chunks)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_chunks = chunks[start:end]
            batch_embeddings = embeddings[start:end]

            documents = []
            ids = []
            metadatas = []

            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                documents.append(chunk["text"])
                ids.append(chunk["chunk_id"])
                metadatas.append({
                    "source": chunk["source"],
                    "chunk_id": chunk["chunk_id"],
                })

            self.collection.add(
                documents=documents,
                embeddings=batch_embeddings,
                ids=ids,
                metadatas=metadatas,
            )

        print(f"  ✓ 已存入 {total} 个文档块到集合 '{self.collection_name}'")

    def query(self, query_embedding: List[float], top_k: int = 5) -> dict:
        """
        向量相似度检索

        Returns:
            {
                "documents": [[文本列表]],
                "metadatas": [[元数据列表]],
                "distances": [[距离列表]],
            }
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        return results

    def count(self) -> int:
        """返回存储的文档块总数"""
        return self.collection.count()

    def clear(self) -> None:
        """清空集合中的所有数据"""
        # 删除并重建集合
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  ✓ 集合 '{self.collection_name}' 已清空")
