"""
查询规划器 — 意图分类 + 查询策略编排

双层分类器: 本地正则优先 (<1ms, 90%覆盖) → LLM 兜底 (10%边界)
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class Intent(Enum):
    CLAUSE_LOOKUP = "clause"
    TABLE_QUERY = "table"
    XREF_TRACE = "xref"
    HIERARCHY_NAV = "hierarchy"
    REQUIREMENT_EXTRACT = "requirement"  # ✨ 新增：提取所有要求
    SEMANTIC = "semantic"


@dataclass
class QueryStep:
    """查询计划中的一步"""
    action: str          # "lookup_clause" | "search_tables" | "trace_xref" | "semantic_search" | "extract_all"
    target: str = ""     # 条款号/表格编号/关键词
    params: dict = field(default_factory=dict)


@dataclass
class QueryPlan:
    """查询执行计划"""
    intent: Intent
    strategy: str        # "direct_lookup" | "table_search" | "xref_trace" | "hierarchy" | "requirement_extract" | "semantic"
    steps: List[QueryStep] = field(default_factory=list)
    confidence: float = 1.0
    needs_agent: bool = False


class QueryPlanner:
    """查询意图识别 + 策略规划"""

    def plan(self, query: str) -> QueryPlan:
        """分析查询，返回执行计划"""
        # 第一层：本地规则（O(1)，零延迟）
        intent = self._local_classify(query)
        if intent:
            return self._build_plan(intent, query)

        # 第二层：LLM 分类（约 10% 边界情况，Phase 4 先跳过）
        return self._build_plan(Intent.SEMANTIC, query)

    def _local_classify(self, query: str) -> Optional[Intent]:
        """本地正则分类，覆盖 90%+ 常规查询"""
        q = query.strip()

        # 条款号查询
        if re.search(r'§\s*\d|第\s*\d+[\.\d]*\s*条|（[一二三四五六七八九十]+）', q):
            return Intent.CLAUSE_LOOKUP

        # 要求提取（新增意图）
        if any(kw in q for kw in ['提取要求', '投标人须', '资格条件', '硬性要求']):
            return Intent.REQUIREMENT_EXTRACT

        # 层级导航（先于表格，避免"有哪些"误判）
        if re.search(r'第\s*[一二三四五六七八九十\d]+\s*[章篇卷]', q):
            return Intent.HIERARCHY_NAV

        # 表格/清单查询
        if any(kw in q for kw in ['清单', '表格', '有哪些', '评分标准']):
            return Intent.TABLE_QUERY

        # 交叉引用
        if any(kw in q for kw in ['引用了', '关联', '相关条款', '参见', '关系', '对比']):
            return Intent.XREF_TRACE

        # 层级导航（模糊）
        if re.search(r'.*部分.*内容', q):
            return Intent.HIERARCHY_NAV

        # 条款号提取（无 § 符号）
        if re.search(r'\d+\.\d+(?:\.\d+)?', q):
            return Intent.CLAUSE_LOOKUP

        return None

    def _build_plan(self, intent: Intent, query: str) -> QueryPlan:
        """按意图构建执行步骤"""
        number = self._extract_number(query)

        if intent == Intent.CLAUSE_LOOKUP:
            return QueryPlan(
                intent=intent,
                strategy="direct_lookup",
                steps=[QueryStep("lookup_clause", number)],
            )

        elif intent == Intent.TABLE_QUERY:
            num = self._extract_table_num(query)
            steps = [QueryStep("search_tables", query)]
            if num:
                steps.insert(0, QueryStep("lookup_table", num))
            return QueryPlan(intent=intent, strategy="table_search", steps=steps)

        elif intent == Intent.XREF_TRACE:
            return QueryPlan(
                intent=intent,
                strategy="xref_trace",
                steps=[QueryStep("trace_xref", number or query)],
                needs_agent=True,
            )

        elif intent == Intent.HIERARCHY_NAV:
            return QueryPlan(
                intent=intent,
                strategy="hierarchy",
                steps=[QueryStep("search_clauses", query)],
            )

        elif intent == Intent.REQUIREMENT_EXTRACT:
            return QueryPlan(
                intent=intent,
                strategy="requirement_extract",
                steps=[
                    QueryStep("search_clauses", "投标人须"),
                    QueryStep("search_clauses", "投标人应"),
                    QueryStep("search_clauses", "投标人必须"),
                    QueryStep("search_tables", "资质"),
                ],
                needs_agent=True,
            )

        else:  # SEMANTIC
            return QueryPlan(
                intent=intent,
                strategy="semantic",
                steps=[QueryStep("semantic_search", query)],
            )

    def _extract_number(self, text: str) -> str:
        m = re.search(r'(§?\s*\d+\.\d+(?:\.\d+)?)', text)
        return m.group(1).replace(' ', '') if m else text[:20]

    def _extract_table_num(self, text: str) -> str:
        m = re.search(r'([A-Z]+-\d+)', text)
        return m.group(1) if m else ""
