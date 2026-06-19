"""
搜索智能体 — 差距检测 + 补充搜索

原则: 纯 Python 类，启发式算法，不引入额外 LLM 成本。
"""
from typing import List, Dict, Optional
from .query_planner import QueryPlan, QueryStep, Intent


class SearchAgent:
    """
    搜索智能体：分析检索结果是否充分，发现缺口后自动补充搜索。

    可访问的工具:
    - 结构化引擎（条款树 + 表格库 + 条款号索引）
    - RAG 向量检索（语义兜底）
    """

    def __init__(self, structured_engine=None, rag_retriever=None):
        self.struct = structured_engine
        self.rag = rag_retriever

    def analyze(self, query: str, plan: QueryPlan,
                initial_results: List[dict]) -> dict:
        """
        分析检索结果是否充分。

        Returns:
            {"sufficient": bool, "gaps": List[str], "suggested_steps": List[QueryStep]}
        """
        gaps = []

        # Gap 1: 条款查询但没找到
        if plan.intent == Intent.CLAUSE_LOOKUP and not initial_results:
            gaps.append("条款未命中，尝试模糊搜索")

        # Gap 2: 表格查询返回空
        if plan.intent == Intent.TABLE_QUERY and not initial_results:
            gaps.append("表格未命中，尝试搜索表格标题关键词")

        # Gap 3: 交叉引用需要溯源
        if plan.intent == Intent.XREF_TRACE and len(initial_results) < 3:
            gaps.append("引用链不完整，尝试反向追踪")

        # Gap 4: 要求提取可能漏了条款
        if plan.intent == Intent.REQUIREMENT_EXTRACT and len(initial_results) < 10:
            gaps.append("提取结果偏少，尝试扩展搜索词")

        if not gaps:
            return {"sufficient": True, "gaps": [], "suggested_steps": []}

        # 生成补充搜索建议
        suggested = []
        for gap in gaps:
            if "模糊搜索" in gap:
                suggested.append(QueryStep("search_clauses", plan.steps[0].target[:30]))
            elif "表格标题" in gap:
                suggested.append(QueryStep("search_tables", plan.steps[-1].target[:20]))
            elif "反向追踪" in gap:
                suggested.append(QueryStep("trace_xref", plan.steps[0].target, {"reverse": True}))

        return {
            "sufficient": False,
            "gaps": gaps,
            "suggested_steps": suggested,
        }

    def execute_step(self, step: QueryStep) -> List[dict]:
        """执行单个查询步骤"""
        if not self.struct:
            return []

        if step.action == "lookup_clause":
            result = self.struct.get_clause(step.target)
            return [result] if result else []

        elif step.action == "search_clauses":
            return self.struct.search_clauses(step.target, limit=20)

        elif step.action == "search_tables":
            return self.struct.search_tables(step.target, limit=10)

        elif step.action == "lookup_table":
            result = self.struct.get_table(step.target)
            return [result] if result else []

        elif step.action == "trace_xref":
            # Phase 0b 实现
            return []

        return []

    def deep_analyze(self, query: str, plan: QueryPlan) -> dict:
        """
        深度分析查询，返回增强后的检索策略。

        用于需要跨章节综合回答的复杂查询。
        """
        # 检测是否需要跨章节
        cross_chapter = plan.intent in (Intent.XREF_TRACE, Intent.REQUIREMENT_EXTRACT)

        # 检测是否需要表格 + 条款联合
        needs_table_and_clause = plan.intent == Intent.TABLE_QUERY

        return {
            "cross_chapter_required": cross_chapter,
            "table_clause_joint": needs_table_and_clause,
            "estimated_complexity": "high" if cross_chapter else "medium",
        }
