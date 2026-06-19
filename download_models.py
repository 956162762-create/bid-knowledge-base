"""从 HuggingFace 下载 RAG 本地模型到 models/ 目录

国内网络建议设置镜像后再运行:
  set HF_ENDPOINT=https://hf-mirror.com
  python download_models.py
"""
import os
import subprocess
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

MODELS = [
    {
        "repo_id": "BAAI/bge-small-zh-v1.5",
        "local_dir": MODELS_DIR / "bge-small-zh-v1.5",
        "desc": "中文嵌入模型 (~100MB)",
    },
    {
        "repo_id": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        "local_dir": MODELS_DIR / "mmarco-mMiniLMv2-L12-H384-v1",
        "desc": "重排序模型 (~480MB)",
    },
]


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("ALL_PROXY", None)

    for item in MODELS:
        print(f"\n>>> 下载 {item['desc']}: {item['repo_id']}")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "huggingface_hub.cli.hf",
                "download",
                item["repo_id"],
                "--local-dir",
                str(item["local_dir"]),
            ],
            check=True,
            env=env,
        )
        print(f"    已保存到: {item['local_dir']}")

    print("\n全部下载完成。")
    print("请在 config.py 中设置:")
    print('  embedding_provider = "local"')
    print('  local_embedding_model = "./models/bge-small-zh-v1.5"')
    print('  embedding_dimension = 512')
    print('  rerank_provider = "local"')
    print('  local_rerank_model = "./models/mmarco-mMiniLMv2-L12-H384-v1"')


if __name__ == "__main__":
    main()
