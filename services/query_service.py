"""
查询服务 — 意图分类 + 结构化查询 + RAG 兜底
"""
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))


class QueryService:
    """查询总编排器：结构化优先，语义兜底，记忆+规则注入"""

    def __init__(self, data_root: str, memory_manager=None, rules_engine=None):
        self.data_root = data_root
        self.memory = memory_manager
        self.rules = rules_engine

    def save_correction(self, project_id: str, query: str,
                         original_answer: str, corrected_answer: str) -> Optional[int]:
        """保存用户纠错 → 记忆（达到阈值自动转规则）"""
        if not self.memory:
            return None
        return self.memory.store_correction(query, original_answer, corrected_answer)

    def query(self, project_id: str, question: str) -> dict:
        """
        执行查询（完整链路）：
        0. 记忆上下文注入
        1. 规则 pre-retrieval（修改搜索策略）
        2. 意图分类（本地规则优先）
        3. 结构化查询（条款/表格 O(1)）
        4. 语义兜底（RAG）
        5. 规则 post-generation（格式化答案）
        """
        from db.project_repo import ProjectRepo
        repo = ProjectRepo(
            str(Path(self.data_root) / "system.db"),
            self.data_root,
        )
        paths = repo.get_project_paths(project_id)
        if not paths:
            return {"answer": "项目未找到", "intent": "error", "path": "none"}

        # Step 0: 记忆上下文注入 + 规则 pre-retrieval
        memory_context = []
        triggered_rules = []
        additional_searches = []

        if self.rules:
            pre_result = self.rules.apply_pre_retrieval(question)
            triggered_rules = pre_result.get("triggered_rules", [])
            additional_searches = pre_result.get("additional_searches", [])

        if self.memory:
            memory_context = self.memory.get_context_for_query(question)

        # Step 1: 意图分类
        intent = self._classify_intent(question)

        # Step 2: 按意图路由
        result = None
        try:
            from docparse.builder import StructuredEngine
            engine = StructuredEngine(paths["struct_db"])

            if intent == "clause":
                result = self._handle_clause(engine, question)
            elif intent == "table":
                # 规则注入的额外搜索
                result = self._handle_table(engine, question, additional_searches)
            elif intent == "xref":
                result = self._handle_xref(engine, question)
            elif intent == "hierarchy":
                result = self._handle_hierarchy(engine, question)
            else:
                result = self._handle_semantic(project_id, question)
        except Exception as e:
            result = {"answer": f"查询出错: {e}", "intent": intent, "path": "error"}

        # Step 5: 规则 post-generation（格式化答案）
        if self.rules and result:
            result["answer"] = self.rules.apply_post_generation(
                question, result["answer"]
            )

        # 附加元数据
        result["triggered_rules"] = triggered_rules
        if memory_context:
            result["memory_used"] = [m.get("key", "") for m in memory_context]

        return result

    def _extract_keywords(self, query: str) -> list:
        """从查询中提取关键词（去掉疑问词和标点）"""
        import re
        # 去掉常见疑问词和标点
        clean = re.sub(r'[？?，,。！!、\s]+', ' ', query)
        # 去掉疑问后缀
        clean = re.sub(r'(有哪些|是什么|怎么样|怎么|什么|多少|如何|哪个|哪些)', '', clean)
        # 按空格分词
        words = [w.strip() for w in clean.split() if len(w.strip()) >= 2]
        if not words:
            words = [clean.strip()[:8]]
        # 返回从长到短的关键词组合
        return [clean.strip()[:10], clean.strip()[:6]] + words[:3]

    def _classify_intent(self, query: str) -> str:
        """本地正则分类（覆盖 90%+ 查询）"""
        import re
        q = query.strip()

        # 条款/表格编号查询（A-8, DX-4 等表格编号也走结构化）
        if re.search(r'^[A-Z]+-\d+$', q.strip()):
            return "table"

        # 条款号查询
        if re.search(r'§\s*\d|第\s*\d+[\.\d]*\s*条|（[一二三四五六七八九十]+）', q):
            return "clause"

        # 层级导航（先于表格判断，避免"第二卷有哪些内容"误判为表格）
        if re.search(r'第\s*[一二三四五六七八九十\d]+\s*[章篇卷]', q):
            return "hierarchy"

        # 表格/清单查询（层级判断之后）
        if any(kw in q for kw in ["清单", "表格", "有哪些", "评分标准"]):
            return "table"

        # 交叉引用
        if any(kw in q for kw in ["引用了", "关联", "相关条款", "参见", "关系"]):
            return "xref"

        # 层级导航（模糊：XX部分的内容）
        if re.search(r'.*部分.*内容', q):
            return "hierarchy"

        # 尝试提取条款号（无 § 符号的情况）
        if re.search(r'\d+\.\d+(?:\.\d+)?', q):
            return "clause"

        return "semantic"

    def _handle_clause(self, engine, query: str) -> dict:
        """条款号查询 — O(1)"""
        import re
        # 提取条款号
        m = re.search(r'(§?\s*\d+\.\d+(?:\.\d+)?)', query)
        if not m:
            m = re.search(r'(第\s*\d+[\.\d]*\s*条)', query)
        if not m:
            return {"answer": "未能识别条款号", "intent": "clause", "path": "structured"}

        number = m.group(1).replace(" ", "")
        t0 = time.perf_counter()
        clause = engine.get_clause(number)

        if not clause:
            return {
                "answer": f"未找到条款 {number}",
                "intent": "clause", "path": "structured",
                "sources": []
            }

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "answer": f"**{clause['number']} {clause['title']}**\n\n"
                      f"{clause.get('content', '(正文为空)')}\n\n"
                      f"*路径: {clause['path']}*",
            "intent": "clause",
            "path": "structured",
            "sources": [{
                "clause_number": clause["number"],
                "title": clause["title"],
                "path": clause["path"],
                "content_preview": clause.get("content", "")[:200],
            }],
        }

    def _handle_table(self, engine, query: str, additional_searches: list = None) -> dict:
        """表格查询（含规则注入的额外搜索）"""
        import re
        table = None

        # 优先查规则注入的表格编号
        for num in (additional_searches or []):
            table = engine.get_table(num)
            if table:
                break

        # 其次尝试从查询中提取表格编号
        if not table:
            m = re.search(r'([A-Z]+-\d+)', query)
            if m:
                table = engine.get_table(m.group(1))

        if not table:
            # 关键词搜索：从查询中提取 2-4 个字的实词
            keywords = self._extract_keywords(query)
            tables = []
            for kw in keywords:
                tables = engine.search_tables(kw, limit=10)
                if tables:
                    break
            if not tables:
                # 最后尝试原始查询的前 8 个字
                tables = engine.search_tables(query[:8], limit=5)
            if not tables:
                return {"answer": "未找到相关表格", "intent": "table", "path": "structured"}
            table = tables[0]

        # 将表格转为 Markdown
        md = f"**{table.get('title', '表格')}**"
        if table.get('chapter_ref'):
            md += f"  (来自 {table['chapter_ref']})"
        md += "\n\n"

        rows = table.get('rows', [])
        checkbox_map = table.get('checkbox_map', {})
        if rows:
            md += "| " + " | ".join(rows[0]) + " |\n"
            md += "|" + "|".join(["---"] * len(rows[0])) + "|\n"
            for ri, row in enumerate(rows[1:]):
                cells = []
                for ci, cell in enumerate(row):
                    key = f"{ri+1}_{ci}"
                    if key in checkbox_map:
                        prefix = "[✓]" if checkbox_map[key] else "[ ]"
                        cells.append(f"{prefix} {cell}" if cell else prefix)
                    else:
                        cells.append(cell)
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

    def _handle_xref(self, engine, query: str) -> dict:
        """交叉引用查询 — Phase 0b 实现"""
        return {"answer": "交叉引用查询将在 Phase 0b 实现", "intent": "xref", "path": "structured"}

    def _handle_hierarchy(self, engine, query: str) -> dict:
        """层级导航"""
        clauses = engine.search_clauses(query, limit=10)
        if not clauses:
            return {"answer": "未找到匹配的章节", "intent": "hierarchy", "path": "structured"}

        lines = []
        for c in clauses[:10]:
            indent = "  " * c["level"]
            lines.append(f"{indent}- **{c['number']}** {c['title']}  `{c['path']}`")

        return {
            "answer": "\n".join(lines),
            "intent": "hierarchy",
            "path": "structured",
        }

    def _handle_semantic(self, project_id: str, query: str) -> dict:
        """语义兜底 — 走 RAG"""
        return {
            "answer": "语义搜索将在 Phase 0b+2 实现（需集成 RAG 管线）",
            "intent": "semantic",
            "path": "semantic_fallback",
        }
