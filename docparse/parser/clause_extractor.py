"""
条款提取器 — 从文档元素序列中识别条款层级，构建条款节点树

层级体系（招投标文件）：
  Level 1: 卷 (Volume)     eg. "第一卷  投标人须知及投标文件格式"
  Level 2: 篇 (Part)       eg. "第1篇 投标人须知"
  Level 3: 章 (Chapter)    eg. "第六章  特别标准要求"
  Level 4: 节 (Section)    eg. "§6.1" / "6.1  安全管理"
  Level 5: 条 (Clause)     eg. "§6.1.16" / "6.1.16  危险性较大的分部分项工程清单"
  Level 6: 款 (SubClause)  eg. "（一）" / "(1)"
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .docx_parser import ParaElement, TableElement


@dataclass
class ClauseNode:
    """条款树的节点"""
    id: int = 0
    parent_id: Optional[int] = None
    node_type: str = ""                # volume / part / chapter / section / clause / subclause
    number: str = ""                   # "§6.1.16" / "第一卷" / "（一）"
    title: str = ""                    # 条款标题
    content: str = ""                  # 条款正文（该节点下的段落文本）
    level: int = 0                     # 0=卷, 1=篇, 2=章, 3=节, 4=条, 5=款
    page_start: Optional[int] = None
    path: str = ""                     # eg. "/第一卷/第1篇/第六章/§6.1/§6.1.16"
    is_red: bool = False               # 红色字体（工务署 = 重点）
    metadata: Dict = field(default_factory=dict)


class ClauseExtractor:
    """从 docx 元素序列中提取条款层级"""

    # 层级模式匹配（优先级从高到低）
    PATTERNS = [
        # Level 1: 卷
        (1, re.compile(r'^第[一二三四五六七八九十\d]+卷')),
        # Level 1 alt: "第一卷" without 卷 suffix in heading
        (1, re.compile(r'^第[一二三四五六七八九十\d]+卷\s')),

        # Level 2: 篇
        (2, re.compile(r'^第\d+篇')),
        (2, re.compile(r'^第[一二三四五六七八九十]+篇')),

        # Level 3: 章
        (3, re.compile(r'^第[一二三四五六七八九十\d]+章')),

        # Level 4: 节 (§X.Y 格式，如 §6.1)
        (4, re.compile(r'^§?\d+\.\d+(?=\s|$)')),
        # Level 4 alt: "6.1  安全管理" 这种章节标题
        (4, re.compile(r'^\d+\.\d+(?:\s+\S|$)')),

        # Level 5: 条 (§X.Y.Z 格式，如 §6.1.16)
        (5, re.compile(r'^§?\d+\.\d+\.\d+(?=\s|$)')),
        (5, re.compile(r'^\d+\.\d+\.\d+(?:\s+\S|$)')),

        # Level 6: 款 (（一）, （二）, (1), (2) 等)
        (6, re.compile(r'^（[一二三四五六七八九十\d]+）')),
        (6, re.compile(r'^\([a-z\d]+\)')),
    ]

    # 从 outline_level 映射到我们的层级
    OUTLINE_TO_LEVEL = {
        0: 0,   # Title → Volume
        1: 2,   # Heading 1 → Chapter
        2: 3,   # Heading 2 → Section
        3: 4,   # Heading 3 → Clause
        4: 5,   # Heading 4 → SubClause
        5: 5,
        6: 5,
    }

    def __init__(self):
        self._nodes: List[ClauseNode] = []
        self._id_counter = 1
        self._level_stack = []  # 当前层级栈 [(node_id, level), ...]

    def extract(self, elements: List) -> List[ClauseNode]:
        """主入口：从元素序列中提取条款树"""
        self._nodes = []
        self._id_counter = 1
        self._level_stack = []

        current_node_id = None  # 当前正在填充正文的节点

        for elem in elements:
            if isinstance(elem, ParaElement):
                level, number, title = self._classify(elem)

                if level >= 0:
                    # 这是一个标题 → 创建新节点
                    node = self._create_node(level, number, title, elem)
                    self._nodes.append(node)
                    current_node_id = node.id
                elif current_node_id is not None:
                    # 正文段落 → 追加到当前节点的 content
                    for node in self._nodes:
                        if node.id == current_node_id:
                            if node.content:
                                node.content += "\n"
                            node.content += elem.text
                            break

        return self._nodes

    def _classify(self, para: ParaElement) -> tuple:
        """
        分类一个段落的层级。
        返回 (level, number, title)，如果不是标题则 level=-1。
        """
        text = para.text.strip()

        # 方法 1: 使用 Word 的 outline level
        if para.outline_level >= 0:
            level = self.OUTLINE_TO_LEVEL.get(para.outline_level, -1)
            if level >= 0:
                number = self._extract_number(text) or text[:40]
                return (level, number, text[:80])

        # 方法 2: 正则模式匹配
        for level, pattern in self.PATTERNS:
            m = pattern.match(text)
            if m:
                number = self._extract_number(text) or m.group(0)
                # 标题 = 去掉编号后的文本
                title = text[m.end():].strip().lstrip(" .·").strip()
                if not title:
                    title = text[:60]
                return (level, number, title)

        # 不是标题
        return (-1, "", "")

    def _create_node(self, level: int, number: str, title: str, para: ParaElement) -> ClauseNode:
        """创建新条款节点，处理层级栈"""
        node_id = self._id_counter
        self._id_counter += 1

        # 确定父节点
        parent_id = None
        while self._level_stack and self._level_stack[-1][1] >= level:
            self._level_stack.pop()
        if self._level_stack:
            parent_id = self._level_stack[-1][0]

        self._level_stack.append((node_id, level))

        # 构建路径
        path = self._build_path(node_id, parent_id, number)

        # 确定节点类型
        type_map = {0: "volume", 1: "volume", 2: "part", 3: "chapter",
                    4: "section", 5: "clause", 6: "subclause"}
        node_type = type_map.get(level, "clause")

        return ClauseNode(
            id=node_id,
            parent_id=parent_id,
            node_type=node_type,
            number=number,
            title=title,
            level=level,
            is_red=para.is_red,
            path=path,
        )

    def _build_path(self, node_id: int, parent_id: Optional[int], number: str) -> str:
        """构建从根到当前节点的路径"""
        parts = []
        # 找到父节点
        current_parent = parent_id
        while current_parent is not None:
            for node in self._nodes:
                if node.id == current_parent:
                    parts.insert(0, node.number or node.title[:30])
                    current_parent = node.parent_id
                    break
            else:
                break
        parts.append(number)
        return "/" + "/".join(parts)

    def _extract_number(self, text: str) -> str:
        """从文本中提取条款编号"""
        # 尝试提取 §X.Y.Z 模式
        m = re.search(r'(§?\d+\.\d+(?:\.\d+)?)', text)
        if m:
            return m.group(1)
        # 尝试提取 第X卷/篇/章
        m = re.search(r'(第[一二三四五六七八九十\d]+[卷篇章])', text)
        if m:
            return m.group(1)
        # 尝试提取 （X）
        m = re.search(r'(（[一二三四五六七八九十\d]+）)', text)
        if m:
            return m.group(1)
        return ""
