"""
DeepSeek API 生成器 — 后备引擎
DeepSeek API 兼容 OpenAI 格式，国内直连，无需翻墙
"""
import os
from typing import List
import requests
from dotenv import load_dotenv
from config import RAGConfig

load_dotenv()


class DeepSeekGenerator:
    """使用 DeepSeek API 生成答案，作为 Ollama 的后备引擎"""

    PROMPT_TEMPLATE = """你是一位知识助手，请根据用户的问题和下列片段生成准确的回答。

用户问题: {query}

相关片段:
{context}

请基于上述内容作答，不要编造信息。如果片段中没有相关信息，请如实说明。"""

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 DEEPSEEK_API_KEY，请在 .env 中设置")

        # 测试连通性
        try:
            r = requests.post(
                self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10,
            )
            if r.status_code == 200:
                print(f"  ✓ DeepSeek 生成器就绪: {self.MODEL}")
            else:
                raise ConnectionError(f"DeepSeek 返回 HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            raise ConnectionError(f"无法连接 DeepSeek API: {e}")

    def generate(self, query: str, chunks: List[dict], verbose: bool = True) -> str:
        """基于检索到的上下文生成回答（自动重试）"""
        context = "\n\n".join([chunk["text"] for chunk in chunks])
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)

        if verbose:
            print(f"\n{'='*60}")
            print(f"Prompt to DeepSeek ({self.MODEL}):")
            print("-" * 60)
            print(prompt[:500] + ("..." if len(prompt) > 500 else ""))
            print("=" * 60 + "\n")

        import time
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_output_tokens,
                        "stream": False,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2
                    print(f"  [Retry {attempt}/{max_retries}] DeepSeek API failed ({type(e).__name__}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def generate_stream(self, query: str, chunks: List[dict]):
        """流式生成（后续 UI 使用）"""
        context = "\n\n".join([chunk["text"] for chunk in chunks])
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)

        response = requests.post(
            self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
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
        """使用自定义提示词生成"""
        response = requests.post(
            self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_output_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
