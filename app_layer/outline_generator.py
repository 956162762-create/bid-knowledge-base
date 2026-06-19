"""
技术标大纲生成器 — 基于招标文件提取结果生成技术标目录结构

输入: RequirementExtractor 提取结果 + J-DX-4 评审表
输出: 带来源标注 + 评分权重的技术标大纲
"""
from dataclasses import dataclass, field
from typing import List, Optional
from .requirement_extractor import ExtractedRequirement, TechBidChapter


@dataclass
class OutlineSection:
    """技术标大纲的一个章节"""
    number: str                # "1" / "（1）"
    title: str                 # 章节标题
    source_clauses: List[str]  # 来源条款号
    score_weight: Optional[float] = None  # J-DX-4 评分权重
    prompt: str = ""           # 发给用户的编写提示
    ai_template: str = ""      # LLM 预生成的响应框架（后续 Phase 实现）
    user_content: str = ""     # 用户填写的实际内容


class OutlineGenerator:
    """技术标大纲生成器"""

    def __init__(self, chapters: List[TechBidChapter],
                 requirements: List[ExtractedRequirement] = None,
                 jdx4_table: Optional[dict] = None):
        self.chapters = chapters
        self.requirements = requirements or []
        self.jdx4 = jdx4_table

    def generate(self) -> List[OutlineSection]:
        """生成技术标大纲"""
        sections = []

        for ch in self.chapters:
            # 找到对应的强制要求
            related_reqs = [
                r for r in self.requirements
                if any(kw in (r.content + r.clause_ref)
                      for kw in self._extract_keywords(ch.title))
            ]

            source_clauses = list(set(r.clause_ref for r in related_reqs))[:5]

            # 生成编写提示
            prompt = self._generate_prompt(ch, related_reqs)

            sections.append(OutlineSection(
                number=ch.number,
                title=ch.title,
                source_clauses=source_clauses,
                score_weight=None,  # 后续从 J-DX-4 提取
                prompt=prompt,
            ))

        # 添加危大工程专项方案（第9章）
        sections.append(OutlineSection(
            number="9",
            title="危大工程清单及管理措施",
            source_clauses=["§6.1.16", "A-8"],
            prompt="根据招标文件 A-8 清单和 §6.1.16 要求，编制危大工程专项方案。"
                   "列出本项目涉及的危大工程（参照 A-8 中打 [✓] 的条目），"
                   "并逐项说明安全管理措施。",
        ))

        # 添加附件/其他资料（第10章）
        sections.append(OutlineSection(
            number="10",
            title="招标人要求提供的其他资料",
            source_clauses=[],
            prompt="根据招标文件第3篇要求，提供安全生产专项方案、人员配备、"
                   "重难点分析、资源投入计划、工期管控方案、工人工资保障方案等。",
        ))

        return sections

    def _generate_prompt(self, chapter: TechBidChapter,
                         reqs: List[ExtractedRequirement]) -> str:
        """为每个章节生成编写提示"""
        base = f"请根据招标文件要求，编写「{chapter.title}」章节。"

        if reqs:
            base += "\n参考条款: " + ", ".join(
                r.clause_ref for r in reqs[:3]
            )

        # 特殊章节的额外提示
        if "诚信" in chapter.title:
            base += "\n需提供近一年诚信履约记录（评价时间不早于招标公告发布前一年）。"
        elif "设计管理" in chapter.title:
            base += "\n需说明为加强项目品质管控采取的设计管理措施。"
        elif "重点和难点" in chapter.title:
            base += "\n需分析本工程施工重点和难点，并提出针对性保证措施。"
        elif "劳动力" in chapter.title:
            base += "\n需提供劳动力组织计划和工人生活区计划。"
        elif "施工进度" in chapter.title:
            base += "\n需响应招标文件的工期要求，提供施工进度计划和工期保证措施。"
        elif "工程质量" in chapter.title:
            base += "\n需提供质量保证措施、拆除工程和保护性拆除施工保证措施。"
        elif "安全生产" in chapter.title:
            base += "\n需提供安全生产、文明施工、环境保护、室内防尘、施工通风等保证措施。"
        elif "施工现场" in chapter.title:
            base += "\n需提供施工现场平面布置、人机料运输组织、临时办公布置。"

        return base

    def _extract_keywords(self, text: str) -> List[str]:
        """从章节标题提取搜索关键词"""
        import re
        clean = re.sub(r'[、，,。！!]', ' ', text)
        return [w.strip() for w in clean.split() if len(w.strip()) >= 2][:5]

    def to_markdown(self, sections: List[OutlineSection] = None) -> str:
        """将大纲导出为 Markdown"""
        if sections is None:
            sections = self.generate()

        md = "# 技术标大纲\n\n"
        for s in sections:
            md += f"## {s.number} {s.title}\n\n"
            md += f"**来源条款:** {', '.join(s.source_clauses) if s.source_clauses else '招标文件第3篇'}\n\n"
            md += f"> {s.prompt}\n\n"
            md += "---\n\n"
        return md
