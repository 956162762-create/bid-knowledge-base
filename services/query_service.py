"""
查询服务 — 强化检索 + 大模型统一生成

流程:
  1. 意图规划 (QueryPlanner)
  2. 多路检索 (结构化 + 向量 RAG + SearchAgent 补搜)
  3. 大模型综合生成 (DeepSeek)
"""
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.query_planner import QueryPlanner, QueryPlan, Intent
from agent.search_agent import SearchAgent


class QueryService:
    """查询总编排器：检索增强 + LLM 生成"""

    CONVERSATIONAL_PATTERNS = [
        r"^(你好|您好|hi|hello|hey|在吗|谢谢|感谢|你是谁|你能做什么)[\?？!！。]*$",
        r"^(早上好|下午好|晚上好)[\?？!！。]*$",
    ]

    def __init__(self, data_root: str, memory_manager=None, rules_engine=None):
        self.data_root = data_root
        self.memory = memory_manager
        self.rules = rules_engine
        self.planner = QueryPlanner()
        self._generator = None
        self._embedder_cache: Dict[str, Any] = {}
        self._vector_store_cache: Dict[str, Any] = {}

    def save_correction(self, project_id: str, query: str,
                         original_answer: str, corrected_answer: str) -> Optional[int]:
        if not self.memory:
            return None
        return self.memory.store_correction(query, original_answer, corrected_answer)

    def query(self, project_id: str, question: str) -> dict:
        from db.project_repo import ProjectRepo
        repo = ProjectRepo(
            str(Path(self.data_root) / "system.db"),
            self.data_root,
        )
        paths = repo.get_project_paths(project_id)
        if not paths:
            return {"answer": "项目未找到", "intent": "error", "path": "none", "sources": []}

        memory_context = []
        triggered_rules = []
        additional_searches = []

        if self.rules:
            pre_result = self.rules.apply_pre_retrieval(question)
            triggered_rules = pre_result.get("triggered_rules", [])
            additional_searches = pre_result.get("additional_searches", [])

        if self.memory:
            memory_context = self.memory.get_context_for_query(question)

        plan = self.planner.plan(question)
        intent = plan.intent.value
        print(f"[query] intent={intent} strategy={plan.strategy} q='{question[:50]}'")

        # 闲聊/问候：直接 LLM，不做检索
        if self._is_conversational(question):
            has_docs = self._project_has_documents(paths)
            result = self._synthesize(question, [], memory_context, "chat", has_docs)
            result["triggered_rules"] = triggered_rules
            if memory_context:
                result["memory_used"] = [m.get("key", "") for m in memory_context]
            result.setdefault("sources", [])
            if self.rules:
                result["answer"] = self.rules.apply_post_generation(question, result["answer"])
            return result

        # 精确编号快路径：A-8 / §6.1.16 等，直接返回结构化结果
        fast = self._try_fast_lookup(paths, question, intent, additional_searches)
        if fast:
            result = fast
        else:
            result = self._answer_with_retrieval_and_llm(
                project_id, question, paths, plan,
                memory_context, additional_searches,
            )

        if self.rules and result:
            result["answer"] = self.rules.apply_post_generation(question, result["answer"])

        result["triggered_rules"] = triggered_rules
        if memory_context:
            result["memory_used"] = [m.get("key", "") for m in memory_context]
        result.setdefault("sources", [])
        return result

    # ── LLM ─────────────────────────────────────────────

    def _get_generator(self):
        if self._generator is None:
            from deepseek_generator import DeepSeekGenerator
            self._generator = DeepSeekGenerator.get_shared()
        return self._generator

    def _memory_to_text(self, memory_context: List[dict]) -> str:
        if not memory_context:
            return ""
        lines = []
        for m in memory_context[:5]:
            key = m.get("key", "")
            val = m.get("value", "")
            if isinstance(val, dict):
                val = val.get("corrected", val)
            lines.append(f"- {key}: {val}")
        return "历史纠错/记忆:\n" + "\n".join(lines)

    def _is_conversational(self, query: str) -> bool:
        q = query.strip()
        if len(q) <= 12:
            for pat in self.CONVERSATIONAL_PATTERNS:
                if re.match(pat, q, re.IGNORECASE):
                    return True
        return False

    def _synthesize(
        self,
        question: str,
        context_parts: List[str],
        memory_context: List[dict],
        intent: str,
        has_docs: bool,
    ) -> dict:
        extra = self._memory_to_text(memory_context)
        try:
            gen = self._get_generator()
            if not context_parts and self._is_conversational(question):
                answer = gen.chat(
                    question,
                    system=(
                        gen.SYSTEM_PROMPT
                        + " 用户可能在打招呼或闲聊。请友好回应，并简要介绍你可以："
                        "分析招标文件、查询条款与表格、解答投标相关问题、辅助技术标编制。"
                    ),
                )
                return {"answer": answer, "intent": "chat", "path": "llm_chat", "sources": []}

            if not context_parts:
                answer = gen.chat(
                    question,
                    system=(
                        gen.SYSTEM_PROMPT
                        + (" 当前项目已上传招标文件，但未检索到直接匹配内容。" if has_docs
                           else " 当前项目尚未上传招标文件。")
                        + "请友好回答，并建议用户尝试条款号(如6.1.16)、表格编号(如A-8)或更具体的关键词。"
                    ),
                )
                return {"answer": answer, "intent": intent, "path": "llm_no_context", "sources": []}

            answer = gen.generate_from_context(
                question, context_parts, extra_system=extra,
            )
            return {"answer": answer, "intent": intent, "path": "llm_rag", "sources": []}

        except Exception as e:
            print(f"[query] LLM failed: {e}")
            if context_parts:
                fallback = "根据检索到的资料，整理如下：\n\n" + "\n\n---\n\n".join(
                    context_parts[:5]
                )
                return {"answer": fallback, "intent": intent, "path": "retrieval_only", "sources": []}
            return {
                "answer": (
                    "暂时无法连接大模型服务，请检查 .env 中的 DEEPSEEK_API_KEY。\n\n"
                    "你也可以尝试：\n"
                    "- 条款号查询，如 `6.1.16`\n"
                    "- 表格编号，如 `A-8`\n"
                    "- 更短的关键词，如 `基坑`"
                ),
                "intent": intent,
                "path": "error",
                "sources": [],
            }

    # ── 检索 ─────────────────────────────────────────────

    def _models_dir(self) -> Path:
        return Path(__file__).parent.parent / "models" / "bge-small-zh-v1.5"

    def _make_rag_config(self, project_id: str, chroma_path: str):
        class _cfg:
            embedding_provider = "local"
            local_embedding_model = str(Path(__file__).parent.parent / "models" / "bge-small-zh-v1.5")
            embedding_dimension = 384
            normalize_embeddings = True
            chroma_persist_dir = chroma_path
            chroma_collection_name = f"project_{project_id}"
            retrieval_top_k = 8
            temperature = 0.3
            max_output_tokens = 2048
        return _cfg()

    def _chroma_has_data(self, chroma_path: str, project_id: str) -> bool:
        if not chroma_path or not os.path.isdir(chroma_path):
            return False
        try:
            from vector_store import VectorStore
            cfg = self._make_rag_config(project_id, chroma_path)
            vs = VectorStore(cfg)
            return vs.count() > 0
        except Exception:
            return bool(os.listdir(chroma_path))

    def _get_retriever(self, project_id: str, chroma_path: str):
        if not self._chroma_has_data(chroma_path, project_id):
            return None
        if project_id in self._embedder_cache:
            from retriever import Retriever
            cfg = self._make_rag_config(project_id, chroma_path)
            return Retriever(
                self._embedder_cache[project_id],
                self._vector_store_cache[project_id],
                cfg,
            )
        try:
            from embedder import create_embedder
            from vector_store import VectorStore
            from retriever import Retriever

            cfg = self._make_rag_config(project_id, chroma_path)
            embedder = create_embedder(cfg)
            vectordb = VectorStore(cfg)
            self._embedder_cache[project_id] = embedder
            self._vector_store_cache[project_id] = vectordb
            return Retriever(embedder, vectordb, cfg)
        except Exception as e:
            print(f"[query] retriever init failed: {e}")
            return None

    def _rag_retrieve(self, project_id: str, query: str, chroma_path: str, top_k: int = 8) -> List[dict]:
        retriever = self._get_retriever(project_id, chroma_path)
        if not retriever:
            return []
        try:
            return retriever.retrieve(query, top_k=top_k)
        except Exception as e:
            print(f"[query] RAG retrieve failed: {e}")
            return []

    def _extract_keywords(self, query: str) -> list:
        clean = re.sub(r"[？?，,。！!、\s]+", "", query)
        q_words = ["有哪些", "是什么", "怎么样", "怎么", "有什么", "什么", "多少", "如何", "哪个", "哪些"]
        for w in q_words:
            clean = clean.replace(w, "")
        if not clean.strip():
            return [query[:8]]

        keywords = []
        seen = set()
        for win in [2, 3, 4]:
            for i in range(len(clean) - win + 1):
                kw = clean[i:i + win]
                if kw not in seen:
                    seen.add(kw)
                    keywords.append(kw)
        if clean[:10] not in seen:
            keywords.insert(0, clean[:10])
        return keywords[:15]

    def _item_to_context(self, item: dict, kind: str) -> str:
        if kind == "clause":
            return (
                f"[条款 {item.get('number', '')}] {item.get('title', '')}\n"
                f"路径: {item.get('path', '')}\n"
                f"{item.get('content', '')[:1200]}"
            )
        if kind == "table":
            title = item.get("title") or item.get("table_number") or "表格"
            ref = item.get("chapter_ref") or item.get("path") or ""
            rows = item.get("rows") or []
            lines = [f"[表格 {item.get('table_number', title)}] {title}  来源: {ref}"]
            checkbox_map = item.get("checkbox_map") or {}
            for ri, row in enumerate(rows[:15]):
                cells = []
                for ci, cell in enumerate(row):
                    key = f"{ri}_{ci}"
                    if key in checkbox_map:
                        prefix = "[x]" if checkbox_map[key] else "[ ]"
                        cells.append(f"{prefix}{cell}" if cell else prefix)
                    else:
                        cells.append(str(cell))
                lines.append(" | ".join(cells))
            return "\n".join(lines)
        if kind == "rag":
            src = item.get("source") or item.get("chunk_id") or "向量检索"
            return f"[文档片段 {src}]\n{item.get('text', '')[:1200]}"
        return str(item)[:1200]

    def _result_to_source(self, item: dict, kind: str) -> dict:
        if kind == "clause":
            return {
                "clause_number": item.get("number", ""),
                "title": item.get("title", ""),
                "path": item.get("path", ""),
            }
        if kind == "table":
            return {
                "table_number": item.get("table_number", ""),
                "title": item.get("title", ""),
                "path": item.get("chapter_ref") or item.get("path", ""),
            }
        return {"title": item.get("source", ""), "path": item.get("chunk_id", "")}

    def _dedupe_sources(self, sources: List[dict]) -> List[dict]:
        seen = set()
        out = []
        for s in sources:
            key = (s.get("clause_number"), s.get("table_number"), s.get("title"), s.get("path"))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out[:8]

    def _retrieve_context(
        self,
        project_id: str,
        question: str,
        paths: dict,
        plan: QueryPlan,
        additional_searches: List[str],
    ) -> tuple[List[str], List[dict]]:
        from docparse.builder import StructuredEngine
        engine = StructuredEngine(paths["struct_db"])
        chroma_path = paths.get("chroma_path") or paths.get("chroma_dir", "")

        retriever = None
        if self._chroma_has_data(chroma_path, project_id):
            class _R:
                def retrieve(self, q, top_k=8):
                    return self._outer._rag_retrieve(project_id, q, chroma_path, top_k)
            _R._outer = self
            retriever = _R()

        agent = SearchAgent(structured_engine=engine, rag_retriever=retriever)

        collected: List[tuple] = []  # (kind, item)

        # 规则注入的表格优先查
        for num in additional_searches or []:
            table = engine.get_table(num)
            if table:
                collected.append(("table", table))

        # 执行计划步骤
        for step in plan.steps:
            for item in agent.execute_step(step):
                if not item:
                    continue
                if step.action in ("lookup_clause", "search_clauses"):
                    collected.append(("clause", item))
                elif step.action in ("lookup_table", "search_tables"):
                    collected.append(("table", item))

        # 关键词扩展检索（提升召回）
        keywords = self._extract_keywords(question)
        for kw in keywords[:6]:
            for c in engine.search_clauses(kw, limit=3):
                collected.append(("clause", c))
            for t in engine.search_tables(kw, limit=2):
                collected.append(("table", t))

        # 向量语义检索
        rag_chunks = self._rag_retrieve(project_id, question, chroma_path, top_k=8)
        for chunk in rag_chunks:
            collected.append(("rag", chunk))

        # SearchAgent 缺口补搜
        flat_results = [{"kind": k, "item": v} for k, v in collected]
        analysis = agent.analyze(question, plan, flat_results)
        if not analysis.get("sufficient"):
            for step in analysis.get("suggested_steps", []):
                for item in agent.execute_step(step):
                    if step.action in ("lookup_clause", "search_clauses"):
                        collected.append(("clause", item))
                    elif step.action in ("lookup_table", "search_tables"):
                        collected.append(("table", item))

        # 去重
        seen_clauses = set()
        seen_tables = set()
        seen_rag = set()
        context_parts = []
        sources = []

        for kind, item in collected:
            if kind == "clause":
                key = item.get("number")
                if not key or key in seen_clauses:
                    continue
                seen_clauses.add(key)
            elif kind == "table":
                key = item.get("table_number") or item.get("title")
                if not key or key in seen_tables:
                    continue
                seen_tables.add(key)
            else:
                key = item.get("chunk_id") or item.get("text", "")[:40]
                if key in seen_rag:
                    continue
                seen_rag.add(key)

            context_parts.append(self._item_to_context(item, kind))
            sources.append(self._result_to_source(item, kind))

        return context_parts[:12], self._dedupe_sources(sources)

    def _answer_with_retrieval_and_llm(
        self,
        project_id: str,
        question: str,
        paths: dict,
        plan: QueryPlan,
        memory_context: List[dict],
        additional_searches: List[str],
    ) -> dict:
        context_parts, sources = self._retrieve_context(
            project_id, question, paths, plan, additional_searches,
        )
        has_docs = self._project_has_documents(paths)
        result = self._synthesize(
            question, context_parts, memory_context,
            plan.intent.value, has_docs,
        )
        result["sources"] = sources or result.get("sources", [])
        return result

    def _project_has_documents(self, paths: dict) -> bool:
        try:
            import sqlite3
            conn = sqlite3.connect(paths["meta_db"])
            n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            conn.close()
            return n > 0
        except Exception:
            return False

    # ── 快路径 ───────────────────────────────────────────

    def _try_fast_lookup(
        self,
        paths: dict,
        question: str,
        intent: str,
        additional_searches: List[str],
    ) -> Optional[dict]:
        """精确编号查询：跳过 LLM，直接返回格式化内容"""
        from docparse.builder import StructuredEngine
        engine = StructuredEngine(paths["struct_db"])
        q = question.strip()

        if re.match(r"^[A-Z]+-\d+$", q, re.IGNORECASE):
            table = engine.get_table(q.upper())
            if table:
                return self._format_table_result(table)

        m = re.match(r"^§?\s*(\d+\.\d+(?:\.\d+)?)$", q)
        if m:
            clause = engine.get_clause(m.group(1))
            if clause:
                return self._format_clause_result(clause)

        if intent == "table" and additional_searches:
            for num in additional_searches:
                table = engine.get_table(num)
                if table:
                    return self._format_table_result(table)

        return None

    def _format_clause_result(self, clause: dict) -> dict:
        return {
            "answer": (
                f"**{clause['number']} {clause['title']}**\n\n"
                f"{clause.get('content', '(正文为空)')}\n\n"
                f"*路径: {clause['path']}*"
            ),
            "intent": "clause",
            "path": "structured",
            "sources": [{
                "clause_number": clause["number"],
                "title": clause["title"],
                "path": clause["path"],
            }],
        }

    def _format_table_result(self, table: dict) -> dict:
        md = f"**{table.get('title', '表格')}**"
        if table.get("chapter_ref"):
            md += f"  (来自 {table['chapter_ref']})"
        md += "\n\n"
        rows = table.get("rows", [])
        checkbox_map = table.get("checkbox_map", {})
        if rows:
            md += "| " + " | ".join(rows[0]) + " |\n"
            md += "|" + "|".join(["---"] * len(rows[0])) + "|\n"
            for ri, row in enumerate(rows[1:]):
                cells = []
                for ci, cell in enumerate(row):
                    key = f"{ri + 1}_{ci}"
                    if key in checkbox_map:
                        prefix = "[x]" if checkbox_map[key] else "[ ]"
                        cells.append(f"{prefix} {cell}" if cell else prefix)
                    else:
                        cells.append(str(cell))
                md += "| " + " | ".join(cells) + " |\n"
        return {
            "answer": md,
            "intent": "table",
            "path": "structured",
            "sources": [{
                "table_number": table.get("table_number", ""),
                "title": table.get("title", ""),
                "path": f"chapter: {table.get('chapter_ref', '')}",
            }],
        }

    def revectorize_project(self, project_id: str) -> dict:
        """重建项目向量索引（修复历史 ingest 失败）"""
        from db.project_repo import ProjectRepo
        from services.project_service import ProjectService

        repo = ProjectRepo(
            str(Path(self.data_root) / "system.db"),
            self.data_root,
        )
        paths = repo.get_project_paths(project_id)
        if not paths:
            return {"status": "error", "message": "项目未找到"}

        import sqlite3
        conn = sqlite3.connect(paths["meta_db"])
        docs = conn.execute("SELECT file_path FROM documents ORDER BY id DESC").fetchall()
        conn.close()
        if not docs:
            return {"status": "error", "message": "项目无已上传文档"}

        ps = ProjectService(
            str(Path(self.data_root) / "system.db"),
            self.data_root,
        )
        chroma_path = paths.get("chroma_path") or paths.get("chroma_dir")
        total = 0
        errors = []
        for (fp,) in docs:
            try:
                ps._vectorize_document(project_id, fp, chroma_path)
                total += 1
            except Exception as e:
                errors.append(str(e))

        count = 0
        if self._chroma_has_data(chroma_path, project_id):
            from vector_store import VectorStore
            cfg = self._make_rag_config(project_id, chroma_path)
            count = VectorStore(cfg).count()

        return {
            "status": "ok" if not errors else "partial",
            "documents": total,
            "chunks": count,
            "errors": errors,
        }
