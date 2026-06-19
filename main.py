"""
RAG 系统 - 主入口脚本 (招投标文件专用)

完整的 RAG 流程:
  1. 加载文档 (document_loader) → 保留表格结构 + 勾选框转文字
  2. 分块 (chunker)
  3. 嵌入 (embedder)
  4. 存储 (vector_store)
  5. 检索 (retriever)
  6. 重排序 (reranker)
  7. 生成答案 (generator: Ollama / Gemini)

用法:
  python main.py --ingest <目录或文件>  索引招投标文件
  python main.py --query "你的问题"     单次查询
  python main.py                        交互式问答
"""

import argparse
import os
import sys
from pathlib import Path

# 将当前目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from config import RAGConfig
from document_loader import DocumentLoader
from chunker import TextChunker, chunk_documents
from embedder import create_embedder
from vector_store import VectorStore
from retriever import Retriever
from reranker import create_reranker
from generator import Generator
from ollama_generator import OllamaGenerator
from deepseek_generator import DeepSeekGenerator


class RAGSystem:
    """RAG 系统主类 - 将所有组件编排在一起"""

    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.embedder = None
        self.vector_store = None
        self.retriever = None
        self.reranker = None
        self.generator = None
        self._initialized = False

    def initialize(self, generator_type: str = "ollama"):
        """初始化所有组件"""
        if self._initialized:
            return

        print("\n初始化 RAG 系统...\n")

        self.embedder = create_embedder(self.config)
        self.vector_store = VectorStore(self.config)
        self.retriever = Retriever(self.embedder, self.vector_store, self.config)
        self.reranker = create_reranker(self.config)

        # 生成器自动后备链: Ollama → DeepSeek → Gemini
        if generator_type == "auto":
            for gen_cls, name in [
                (OllamaGenerator, "Ollama 本地 (qwen3:32b)"),
                (DeepSeekGenerator, "DeepSeek API"),
                (Generator, "Gemini API"),
            ]:
                try:
                    self.generator = gen_cls(self.config)
                    print(f"  LLM: {name}")
                    break
                except Exception as e:
                    print(f"  {name} 不可用: {e}")
            else:
                print("  LLM: 全部不可用")
                self.generator = None
        elif generator_type == "ollama":
            self._init_single_generator(OllamaGenerator, "Ollama 本地")
        elif generator_type == "deepseek":
            self._init_single_generator(DeepSeekGenerator, "DeepSeek API")
        elif generator_type == "gemini":
            self._init_single_generator(Generator, "Gemini API")

    def _init_single_generator(self, gen_cls, name):
        try:
            self.generator = gen_cls(self.config)
            print(f"  LLM: {name}")
        except Exception as e:
            print(f"  {name} 不可用: {e}")
            self.generator = None

        self._initialized = True
        count = self.vector_store.count()
        print(f"\nRAG 系统就绪 (已有 {count} 个文档块)\n")

    def ingest_file(self, file_path: str) -> int:
        """索引单个文件"""
        self.initialize()

        print(f"\n📄 加载文档: {file_path}")
        loader = DocumentLoader(file_path)
        content = loader.load()

        # 分块
        chunker = TextChunker(self.config)
        chunks = chunker.split(content)

        # 准备块数据
        source_name = Path(file_path).stem
        chunk_data = [
            {
                "text": chunk,
                "source": str(file_path),
                "chunk_id": f"{source_name}_{i}",
            }
            for i, chunk in enumerate(chunks)
        ]

        # 嵌入并存储
        texts = [c["text"] for c in chunk_data]
        embeddings = self.embedder.embed_batch(texts)
        self.vector_store.add_chunks(chunk_data, embeddings)

        return len(chunks)

    def ingest_directory(self, dir_path: str) -> int:
        """索引目录中的所有文档"""
        self.initialize()

        print(f"\n📂 加载目录: {dir_path}")
        documents = DocumentLoader.load_directory(dir_path)

        if not documents:
            print("  ⚠ 未找到任何文档")
            return 0

        # 分块
        all_chunks = chunk_documents(documents, self.config)

        if not all_chunks:
            print("  ⚠ 分块后为空")
            return 0

        # 嵌入并存储
        texts = [c["text"] for c in all_chunks]
        print(f"  正在为 {len(texts)} 个块生成嵌入向量...")
        embeddings = self.embedder.embed_batch(texts)
        self.vector_store.add_chunks(all_chunks, embeddings)

        return len(all_chunks)

    def query(self, question: str, verbose: bool = True) -> dict:
        """执行完整的 RAG 查询流程"""
        self.initialize()

        if verbose:
            print(f"\n🔍 查询: {question}\n")

        # Step 1: 检索
        if verbose:
            print(f"--- 检索 (top-{self.config.retrieval_top_k}) ---")
        retrieved = self.retriever.retrieve(question)

        if verbose:
            for i, chunk in enumerate(retrieved):
                score = 1 - chunk.get("distance", 1)
                print(f"  [{i}] ({score:.3f}) {chunk['text'][:80]}...")

        # Step 2: 重排序
        if verbose:
            print(f"\n--- 重排序 (top-{self.config.rerank_top_k}) ---")
        reranked = self.reranker.rerank(question, retrieved)

        if verbose:
            for i, chunk in enumerate(reranked):
                print(f"  [{i}] ({chunk['rerank_score']:.4f}) {chunk['text'][:80]}...")

        # Step 3: 生成答案
        answer = None
        if self.generator:
            if verbose:
                print(f"\n--- LLM 生成 ({self.config.llm_model}) ---")
            answer = self.generator.generate(question, reranked, verbose=verbose)
        else:
            answer = "⚠ LLM 生成器不可用 (请设置 GOOGLE_API_KEY)"

        return {
            "question": question,
            "retrieved": retrieved,
            "reranked": reranked,
            "answer": answer,
        }

    def interactive(self):
        """交互式问答循环"""
        self.initialize()

        print("\n" + "=" * 60)
        print("  RAG 交互式问答系统")
        print("  输入问题开始查询，输入 'quit' 或 'exit' 退出")
        print("=" * 60)

        while True:
            try:
                question = input("\n🤔 你的问题: ").strip()
                if not question:
                    continue
                if question.lower() in ("quit", "exit", "q"):
                    print("👋 再见！")
                    break

                result = self.query(question, verbose=False)

                print("\n" + "-" * 50)
                print("📖 回答:")
                print("-" * 50)
                print(result["answer"])
                print("-" * 50)

                # 显示来源
                print("📚 参考来源:")
                sources = set()
                for chunk in result["reranked"]:
                    sources.add(chunk["source"])
                for s in sources:
                    print(f"  • {s}")

            except KeyboardInterrupt:
                print("\n👋 再见！")
                break
            except Exception as e:
                print(f"❌ 错误: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="RAG 系统 - 检索增强生成 (基于 ChromaDB + Gemini)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --demo                  运行完整演示
  python main.py --ingest ./docs         索引文档目录
  python main.py --query "什么是RAG?"    单次查询
  python main.py                         交互式问答
        """,
    )
    parser.add_argument("--ingest", type=str, metavar="PATH", help="索引文档或目录")
    parser.add_argument("--query", type=str, metavar="QUESTION", help="单次查询")
    parser.add_argument("--clear", action="store_true", help="清空数据库后重新索引")
    parser.add_argument("--persist-dir", type=str, default="./bid_doc_db", help="ChromaDB 持久化目录")
    parser.add_argument("--generator", type=str, default="ollama", choices=["ollama", "deepseek", "gemini", "auto"],
                        help="LLM 后端 (默认 ollama，auto=ollama→deepseek→gemini)")

    args = parser.parse_args()

    config = RAGConfig(chroma_persist_dir=args.persist_dir)
    rag = RAGSystem(config)

    if args.clear:
        rag.initialize()
        rag.vector_store.clear()
        print("数据库已清空")

    if args.ingest:
        path = args.ingest
        if os.path.isfile(path):
            count = rag.ingest_file(path)
        else:
            count = rag.ingest_directory(path)
        print(f"索引完成: {count} 个文档块")

    if args.query:
        result = rag.query(args.query, verbose=True)
        print("\n" + "=" * 50)
        print("答案:")
        print("=" * 50)
        print(result["answer"])
        print("=" * 50)
        # 显示来源
        sources = set(c.get("source", "") for c in result["reranked"])
        if sources:
            print("\n参考来源:")
            for s in sources:
                if s:
                    print(f"  · {s}")

    if not args.query and not args.ingest and not args.clear:
        rag.interactive()


if __name__ == "__main__":
    main()
