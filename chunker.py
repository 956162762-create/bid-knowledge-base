"""
文档分块器 - 将长文档拆分为适合检索的语义块
"""
import re
from typing import List
from config import RAGConfig


class TextChunker:
    """文档分块策略: 按段落或固定大小"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.strategy = self.config.chunk_strategy

    def split(self, text: str) -> List[str]:
        """主入口: 根据策略选择分块方法"""
        if self.strategy == "paragraph":
            return self._split_by_paragraph(text)
        elif self.strategy == "fixed_size":
            return self._split_fixed_size(text)
        else:
            raise ValueError(f"未知的分块策略: {self.strategy}")

    def _split_by_paragraph(self, text: str) -> List[str]:
        """
        按段落分块 - 以连续两个换行符为分隔 (与教程仓库一致)

        同时过滤掉纯空白块。
        """
        # 统一换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 按双换行分块
        chunks = text.split("\n\n")
        # 清理并过滤
        result = []
        for chunk in chunks:
            cleaned = chunk.strip()
            if cleaned:
                result.append(cleaned)
        return result

    def _split_fixed_size(self, text: str) -> List[str]:
        """
        固定大小分块 - 按字符数分割，带重叠

        尽量在句号、换行等自然边界处断开。
        """
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap

        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            if end >= len(text):
                chunk = text[start:].strip()
                if chunk:
                    chunks.append(chunk)
                break

            # 尝试在自然边界断开
            chunk_text = text[start:end]
            # 寻找最后一个句号、问号、感叹号或换行
            for sep in ["\n", "。", "！", "？", ".", "!", "?"]:
                last_sep = chunk_text.rfind(sep)
                if last_sep > chunk_size * 0.6:  # 至少保留60%
                    end = start + last_sep + 1
                    break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap

        return chunks


def chunk_documents(documents: List[dict], config: RAGConfig = None) -> List[dict]:
    """
    批量分块: 对多个文档进行分块，保留文档来源信息

    Args:
        documents: [{"path": ..., "content": ...}, ...]
        config: RAG 配置

    Returns:
        [{"text": ..., "source": ..., "chunk_id": ...}, ...]
    """
    chunker = TextChunker(config)
    all_chunks = []

    for doc in documents:
        text_chunks = chunker.split(doc["content"])
        source = doc["path"]

        for i, chunk_text in enumerate(text_chunks):
            all_chunks.append({
                "text": chunk_text,
                "source": source,
                "chunk_id": f"{Path(source).stem}_{i}",
            })

    return all_chunks


from pathlib import Path
