"""
DeepSeek API 生成器 — 后备引擎
DeepSeek API 兼容 OpenAI 格式，国内直连，无需翻墙
"""
import os
import sys
from typing import List, Optional
import requests
from dotenv import load_dotenv
from config import RAGConfig

load_dotenv()


def _safe_print(msg: str) -> None:
    """Windows GBK 终端安全输出"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


class DeepSeekGenerator:
    """使用 DeepSeek API 生成答案，作为 Ollama 的后备引擎"""

    SYSTEM_PROMPT = (
        "你是一位专业的招投标知识库助手，熟悉招标文件、技术标和评标办法。"
        "请基于提供的参考资料回答用户问题，使用清晰的中文。"
        "若参考资料中没有相关信息，请如实说明，不要编造条款或表格内容。"
        "回答应结构清晰，重要条款号、表格编号需明确标注来源。"
    )

    PROMPT_TEMPLATE = """请根据下列参考资料回答用户问题。

用户问题: {query}

参考资料:
{context}

要求:
1. 仅依据参考资料作答，不要编造
2. 引用时标注条款号或表格编号
3. 若资料不足，说明缺失内容并给出可尝试的检索建议
"""

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    _instance: Optional["DeepSeekGenerator"] = None

    def __init__(self, config: RAGConfig = None, verify_on_init: bool = True):
        self.config = config or RAGConfig()
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 DEEPSEEK_API_KEY，请在 .env 中设置")

        if verify_on_init:
            self._ping()

    @classmethod
    def get_shared(cls, config: RAGConfig = None) -> "DeepSeekGenerator":
        if cls._instance is None:
            cls._instance = cls(config, verify_on_init=False)
        return cls._instance

    def _ping(self) -> None:
        try:
            r = requests.post(
                self.BASE_URL,
                headers=self._headers(),
                json={
                    "model": self.MODEL,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10,
            )
            if r.status_code == 200:
                _safe_print(f"  [OK] DeepSeek ready: {self.MODEL}")
            else:
                raise ConnectionError(f"DeepSeek HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            raise ConnectionError(f"无法连接 DeepSeek API: {e}") from e

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict, timeout: int = 120) -> dict:
        import time
        max_retries = 3
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    self.BASE_URL,
                    headers=self._headers(),
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    wait = attempt * 2
                    _safe_print(
                        f"  [Retry {attempt}/{max_retries}] DeepSeek failed "
                        f"({type(e).__name__}), wait {wait}s..."
                    )
                    time.sleep(wait)
        raise last_err

    def chat(
        self,
        user_message: str,
        system: str = None,
        history: List[dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """通用对话（无需检索上下文）"""
        messages = [{"role": "system", "content": system or self.SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        data = self._post({
            "model": self.MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        })
        return data["choices"][0]["message"]["content"].strip()

    def generate(self, query: str, chunks: List[dict], verbose: bool = True) -> str:
        """基于检索到的上下文生成回答"""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            src = chunk.get("source") or chunk.get("title") or f"片段{i}"
            text = chunk.get("text") or chunk.get("content") or str(chunk)
            context_parts.append(f"[{src}]\n{text}")
        return self.generate_from_context(query, context_parts, verbose=verbose)

    def generate_from_context(
        self,
        query: str,
        context_parts: List[str],
        verbose: bool = False,
        extra_system: str = "",
    ) -> str:
        context = "\n\n---\n\n".join(context_parts) if context_parts else "(无参考资料)"
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)
        system = self.SYSTEM_PROMPT
        if extra_system:
            system = f"{system}\n\n{extra_system}"

        if verbose:
            _safe_print(f"\n{'=' * 60}\nPrompt to DeepSeek ({self.MODEL}):\n{prompt[:500]}...\n{'=' * 60}\n")

        data = self._post({
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        })
        return data["choices"][0]["message"]["content"].strip()

    def generate_stream(self, query: str, chunks: List[dict]):
        """流式生成（后续 UI 使用）"""
        context = "\n\n".join([chunk["text"] for chunk in chunks])
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)

        response = requests.post(
            self.BASE_URL,
            headers=self._headers(),
            json={
                "model": self.MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_output_tokens,
                "stream": True,
            },
            timeout=120,
            stream=True,
        )
        for line in response.iter_lines():
            if line and line.startswith(b"data: "):
                data = line[6:]
                if data == b"[DONE]":
                    break
                import json
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta:
                    yield delta["content"]

    def generate_with_custom_prompt(self, prompt: str) -> str:
        data = self._post({
            "model": self.MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        })
        return data["choices"][0]["message"]["content"].strip()
