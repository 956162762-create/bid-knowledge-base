"""
答案生成器 - 基于检索到的上下文调用 LLM 生成最终回答 (与教程仓库一致使用 Gemini)
"""
import os
from typing import List
from google import genai
from dotenv import load_dotenv
from config import RAGConfig

load_dotenv()


class Generator:
    """LLM 答案生成器 - 使用 Google Gemini"""

    PROMPT_TEMPLATE = """你是一位知识助手，请根据用户的问题和下列片段生成准确的回答。

用户问题: {query}

相关片段:
{context}

请基于上述内容作答，不要编造信息。如果片段中没有相关信息，请如实说明。"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()

        api_key = self.config.google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "未找到 GOOGLE_API_KEY！\n"
                "请在 .env 文件中设置: GOOGLE_API_KEY=your-key\n"
                "或设置环境变量: export GOOGLE_API_KEY='your-key'"
            )

        # 配置代理 (翻墙/VPN 代理, 通常为 http://127.0.0.1:7897)
        proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if proxy_url:
            import httpx
            from google.genai.types import HttpOptions
            http_transport = httpx.HTTPTransport(proxy=proxy_url, verify=False)
            http_client = httpx.Client(transport=http_transport)
            self.client = genai.Client(
                api_key=api_key,
                http_options=HttpOptions(httpx_client=http_client),
            )
            print(f"  ✓ LLM 生成器就绪 (通过代理: {proxy_url})")
        else:
            self.client = genai.Client(api_key=api_key)
            print("  ✓ LLM 生成器就绪 (直连)")

        self.model_name = self.config.llm_model

    def generate(self, query: str, chunks: List[dict], verbose: bool = True) -> str:
        """基于检索到的上下文生成回答 (自动重试)"""
        context = "\n\n".join([chunk["text"] for chunk in chunks])
        prompt = self.PROMPT_TEMPLATE.format(query=query, context=context)

        if verbose:
            print("\n" + "=" * 60)
            print("Prompt to LLM:")
            print("-" * 60)
            print(prompt)
            print("=" * 60 + "\n")

        import time
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={
                        "temperature": self.config.temperature,
                        "max_output_tokens": self.config.max_output_tokens,
                    },
                )
                return response.text
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2
                    print(f"  [Retry {attempt}/{max_retries}] API call failed ({type(e).__name__}), "
                          f"waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def generate_with_custom_prompt(self, prompt: str) -> str:
        """使用自定义提示词生成 (高级用法)"""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_output_tokens,
            },
        )
        return response.text
