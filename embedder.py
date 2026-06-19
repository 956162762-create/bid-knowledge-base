"""
嵌入模型 - 将文本转换为向量表示

支持两种后端:
  - GeminiEmbedder: 调用 Google Gemini API (无需下载模型, 推荐)
  - LocalEmbedder: 使用本地 sentence-transformers (需从 HuggingFace 下载)
"""
import os
from typing import List
from dotenv import load_dotenv
from config import RAGConfig

load_dotenv()


class GeminiEmbedder:
    """使用 Google Gemini API 生成文本嵌入 (推荐, 无需下载模型)"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.model_name = self.config.gemini_embedding_model

        from google import genai
        api_key = self.config.google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "未找到 GOOGLE_API_KEY！\n"
                "请在 .env 文件中设置: GOOGLE_API_KEY=your-key\n"
                "或设置环境变量: export GOOGLE_API_KEY='your-key'"
            )
        self.client = genai.Client(api_key=api_key)
        print(f"  ✓ Gemini 嵌入模型就绪: {self.model_name}")

    def embed(self, text: str) -> List[float]:
        """将单段文本转换为向量"""
        result = self.client.models.embed_content(
            model=self.model_name,
            contents=text,
            config={"output_dimensionality": self.config.embedding_dimension},
        )
        return result.embeddings[0].values

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入 (Gemini 的 batchEmbedContents 支持批量)"""
        embeddings = []
        # Gemini embed_content 支持单次传入多个 content
        # 先尝试批量
        try:
            result = self.client.models.embed_content(
                model=self.model_name,
                contents=texts,
                config={"output_dimensionality": self.config.embedding_dimension},
            )
            return [e.values for e in result.embeddings]
        except Exception:
            # 回退到逐个处理
            for text in texts:
                emb = self.embed(text)
                embeddings.append(emb)
            return embeddings


class LocalEmbedder:
    """使用本地 sentence-transformers 模型生成嵌入 (需下载模型)"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.model_name = self.config.local_embedding_model

        from sentence_transformers import SentenceTransformer
        print(f"正在加载本地嵌入模型: {self.model_name} ...")
        self.model = SentenceTransformer(self.model_name)
        dim = self.model.get_embedding_dimension()
        print(f"  ✓ 嵌入模型加载完成 (维度: {dim})")

    def embed(self, text: str) -> List[float]:
        embedding = self.model.encode(
            text,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=True,
        )
        return embeddings.tolist()


# ===== 工厂函数 =====

def create_embedder(config: RAGConfig = None):
    """根据配置创建对应的嵌入器"""
    config = config or RAGConfig()

    if config.embedding_provider == "gemini":
        return GeminiEmbedder(config)
    elif config.embedding_provider == "local":
        return LocalEmbedder(config)
    else:
        raise ValueError(f"未知的嵌入提供者: {config.embedding_provider}")


# 保持向后兼容
Embedder = create_embedder
