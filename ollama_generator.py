"""
Ollama 本地 LLM 生成器 - 替代 Gemini，无需翻墙
"""
import json
from typing import List
import requests
from config import RAGConfig


class OllamaGenerator:
    """使用本地 Ollama 大模型生成答案 (千问/Qwen 等)"""

    PROMPT_TEMPLATE = """你是一位知识助手，请根据用户的问题和下列片段生成准确的回答。

用户问题: {query}

相关片段:
{context}

请基于上述内容作答，不要编造信息。如果片段中没有相关信息，请如实说明。"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.base_url = "http://localhost:11434"
        self.model_name = "qwen3:32b"  # 默认用 32B
        self.temperature = self.config.temperature
        self.max_tokens = self.config.max_output_tokens

        # 检查服务是否可用
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                # 如果 36B 不可用，降级到 32B
                if self.model_name not in models:
                    for m in models:
                        if "qwen" in m:
                            self.model_name = m
                            break
                print(f"  ✓ Ollama 生成器就绪: {self.model_name}")
            else:
                raise ConnectionError(f"Ollama 返回 {r.status_code}")
        except Exception as e:
            raise ConnectionError(f"无法连接 Ollama ({self.base_url}): {e}")

    def generate(self, query: str, chunks: List[dict], verbose: bool = True) -> str:
        """基于检索到的上下文生成回答"""
        context = "\n\n".join([chunk["text"] for chunk in chunks])
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)

        if verbose:
            print("\n" + "=" * 60)
            print(f"Prompt to {self.model_name}:")
            print("-" * 60)
            print(prompt[:500] + ("..." if len(prompt) > 500 else ""))
            print("=" * 60 + "\n")

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300,  # 5 分钟，首次加载模型需要时间
        )
        response.raise_for_status()
        result = response.json()

        return result["message"]["content"]

    def generate_with_custom_prompt(self, prompt: str) -> str:
        """使用自定义提示词生成"""
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=300,  # 5 分钟，首次加载模型需要时间
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
