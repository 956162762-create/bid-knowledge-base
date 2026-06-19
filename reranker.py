"""
重排序器 - 对检索结果进行精细排序

支持三种后端:
  - none:    跳过重排序, 直接返回检索结果
  - gemini:  使用 Gemini API 进行语义重排序 (推荐, 无需下载模型)
  - local:   使用本地 CrossEncoder (需从 HuggingFace 下载)
"""
from typing import List
from config import RAGConfig


class NoReranker:
    """直接返回原始检索结果, 不进行重排序"""

    def rerank(self, query: str, chunks: List[dict], top_k: int = None) -> List[dict]:
        if top_k is None:
            return chunks
        return chunks[:top_k]


class GeminiReranker:
    """使用 Gemini API 对检索结果进行语义相关性打分并重排"""

    PROMPT = """评估以下文档片段与用户查询的相关性。为每个片段打分 (0-10), 分数越高越相关。
只输出 JSON 格式: [{"index": 0, "score": 9.5, "reason": "..."}, ...]

用户查询: {query}

文档片段:
{chunks}

请直接输出 JSON 数组, 不要包含其他内容。"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        from google import genai
        import os
        api_key = self.config.google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("需要 GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model_name = self.config.llm_model
        print(f"  ✓ Gemini 重排序器就绪: {self.model_name}")

    def rerank(self, query: str, chunks: List[dict], top_k: int = None) -> List[dict]:
        if top_k is None:
            top_k = self.config.rerank_top_k
        if not chunks:
            return []

        # 构建重排序提示词
        chunks_text = "\n\n".join(
            f"[{i}]: {chunk['text'][:300]}" for i, chunk in enumerate(chunks)
        )
        prompt = self.PROMPT.format(query=query, chunks=chunks_text)

        import json
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={"temperature": 0, "max_output_tokens": 512},
        )

        try:
            # 尝试解析 JSON 响应
            text = response.text.strip()
            # 提取 JSON 部分 (可能在 markdown 代码块中)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            scores = json.loads(text)
        except json.JSONDecodeError:
            # 解析失败则保持原顺序
            return chunks[:top_k]

        # 按 Gemini 打分排序
        scored = []
        for item in scores:
            idx = item["index"]
            if idx < len(chunks):
                scored.append({**chunks[idx], "rerank_score": float(item["score"])})

        scored.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return scored[:top_k]


class LocalReranker:
    """使用本地 CrossEncoder 模型进行重排序"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.model_name = self.config.local_rerank_model

        from sentence_transformers import CrossEncoder
        print(f"正在加载重排序模型: {self.model_name} ...")
        self.model = CrossEncoder(self.model_name)
        print("  ✓ 重排序模型加载完成")

    def rerank(self, query: str, chunks: List[dict], top_k: int = None) -> List[dict]:
        if top_k is None:
            top_k = self.config.rerank_top_k
        if not chunks:
            return []

        pairs = [(query, chunk["text"]) for chunk in chunks]
        scores = self.model.predict(pairs)

        scored = []
        for chunk, score in zip(chunks, scores):
            scored.append({**chunk, "rerank_score": float(score)})

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]


# ===== 工厂函数 =====

def create_reranker(config: RAGConfig = None):
    """根据配置创建对应的重排序器"""
    config = config or RAGConfig()

    if config.rerank_provider == "none":
        return NoReranker()
    elif config.rerank_provider == "gemini":
        return GeminiReranker(config)
    elif config.rerank_provider == "local":
        return LocalReranker(config)
    else:
        raise ValueError(f"未知的重排序提供者: {config.rerank_provider}")


# 保持向后兼容
Reranker = create_reranker
