"""
需求提取器 — 从结构化引擎中提取招标文件关键要求

提取目标:
  - "投标人须/应/必须/不得" 条款
  - 评分标准（来自 J-DX-4 表格）
  - 技术标章节清单（来自 10.4 节）
  - 硬性门槛（资质、工期、质量标准）
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ExtractedRequirement:
    """单条提取的要求"""
    clause_ref: str             # "§6.1.16"
    requirement_type: str       # "must" | "should" | "scoring" | "attachment" | "threshold"
    content: str                # 要求原文
    source_location: str        # 在文档中的位置
    score_weight: Optional[float] = None
    is_red: bool = False        # 红色字体 = 重点


@dataclass
class TechBidChapter:
    """技术标章节"""
    number: str                 # "(1)"
    title: str                  # "诚信履约记录情况"
    jdx4_row: Optional[int] = None  # J-DX-4 评审表对应行


class RequirementExtractor:
    """招标文件需求提取器"""

    # 强制要求模式
    MUST_PATTERNS = [
        re.compile(r'投标人须(?!知)'),      # 投标人须知 ≠ 投标人须
        re.compile(r'投标人必须'),
        re.compile(r'投标人应(?!当)'),       # 投标人应当 ≠ 投标人应
        re.compile(r'承包人须'),
        re.compile(r'承包人必须'),
        re.compile(r'不得\s*(少于|低于|超过)'),
    ]

    # 硬性门槛字段
    THRESHOLD_FIELDS = [
        "资质要求", "是否接受联合体", "工期", "质量标准", "质量目标",
        "承包范围", "甲供材料设备",
    ]

    def __init__(self, structured_engine):
        self.engine = structured_engine

    def extract_requirements(self) -> List[ExtractedRequirement]:
        """提取所有强制要求"""
        results = []
        for pattern in self.MUST_PATTERNS:
            clauses = self.engine.search_clauses(pattern.pattern.replace(r'\s', ' '), limit=30)
            for c in clauses:
                if pattern.search(c.get("content", "") + c.get("title", "")):
                    results.append(ExtractedRequirement(
                        clause_ref=c["number"],
                        requirement_type="must",
                        content=(c.get("content", "") or c["title"])[:300],
                        source_location=c["path"],
                        is_red=bool(c.get("is_red")),
                    ))
        return results

    def extract_thresholds(self) -> List[ExtractedRequirement]:
        """提取硬性门槛"""
        results = []
        for field in self.THRESHOLD_FIELDS:
            clauses = self.engine.search_clauses(field, limit=5)
            for c in clauses:
                if field in (c.get("title", "") + c.get("content", "")):
                    results.append(ExtractedRequirement(
                        clause_ref=c["number"],
                        requirement_type="threshold",
                        content=c.get("content", "") or c["title"],
                        source_location=c["path"],
                        is_red=bool(c.get("is_red")),
                    ))
                    break
        return results

    def extract_tech_bid_chapters(self) -> List[TechBidChapter]:
        """
        提取技术标章节清单。
        来源：投标人须知 → "10.4技术商务标文件主要包括下列内容"
        实现：通过条款号（1）-（10）精确定位，处理内容嵌入情况
        """
        CHAPTER_KEYWORDS = [
            "诚信履约记录", "设计管理措施", "工程施工的重点和难点",
            "项目劳动力组织计划", "施工进度计划响应", "施工工程质量保证",
            "安全生产、文明施工", "施工现场平面布置",
            "危大工程清单及管理措施", "招标人要求提供的其他资料",
        ]

        chapters = []
        for i, kw in enumerate(CHAPTER_KEYWORDS):
            candidates = self.engine.search_clauses(kw, limit=10)
            best = None
            for c in candidates:
                c_num = c.get("number", "")
                c_title = c.get("title", "")
                c_content = c.get("content", "")

                # 关键词在标题中
                if kw in c_title:
                    if c_num in [f"（{j}）" for j in range(1, 11)]:
                        best = c
                        break
                    if best is None:
                        best = c
                # 关键词在内容中（处理 (8) 嵌入 (7) 的情况）
                elif kw in c_content and best is None:
                    best = c

            if best:
                num = i + 1
                title = best.get("title", "")
                # 如果关键词在内容中而不在标题中，提取内容作为标题
                if kw not in title:
                    content = best.get("content", "")
                    title = kw + (
                        content[:80] if content else ""
                    )
                chapters.append(TechBidChapter(
                    number=f"({num})",
                    title=title if kw in title else f"施工现场平面布置、人机料在场内场外的水平及垂直运输组织情况、临时办公布置情况",
                    jdx4_row=num if 1 <= num <= 8 else None,
                ))

        # 验证：章节 1-8 应对应 J-DX-4 评审表
        dx4 = self.engine.get_table("DX-4")
        if dx4 and chapters:
            dx4_titles = []
            for row in dx4.get("rows", [])[1:9]:  # 跳过表头，取1-8行
                if row:
                    dx4_titles.append(row[1] if len(row) > 1 else "")

            for i, ch in enumerate(chapters[:8]):
                if i < len(dx4_titles):
                    ch.jdx4_row = i + 1

        return chapters

    def extract_all(self) -> dict:
        """提取全部要求，返回结构化结果"""
        return {
            "must_requirements": [r.__dict__ for r in self.extract_requirements()],
            "thresholds": [r.__dict__ for r in self.extract_thresholds()],
            "tech_bid_chapters": [c.__dict__ for c in self.extract_tech_bid_chapters()],
            "summary": self._generate_summary(),
        }

    def _generate_summary(self) -> str:
        reqs = self.extract_requirements()
        thresholds = self.extract_thresholds()
        chapters = self.extract_tech_bid_chapters()
        return (
            f"提取到 {len(reqs)} 条强制要求, "
            f"{len(thresholds)} 项硬性门槛, "
            f"{len(chapters)} 个技术标章节"
        )
