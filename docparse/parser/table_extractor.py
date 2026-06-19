"""
表格提取器 — 从文档元素序列中提取完整表格

保留完整结构：行列、合并单元格、勾选框状态
支持表格标题识别（表格前后的段落可能是标题/caption）
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .docx_parser import ParaElement, TableElement


@dataclass
class ExtractedTable:
    """提取后的表格"""
    id: int = 0
    table_number: str = ""             # "A-8" / "表3-1" / ""
    title: str = ""                    # 表格标题
    caption: str = ""                  # 表头说明
    chapter_ref: str = ""              # 所属条款号，如 "§6.1.16"
    page_number: Optional[int] = None
    rows: List[List[str]] = field(default_factory=list)
    checkbox_map: Dict[str, bool] = field(default_factory=dict)
    merged_cells: List[Dict] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0
    raw_html: str = ""                 # 预渲染的 HTML 表格


class TableExtractor:
    """从元素序列中提取完整表格"""

    # 表格编号模式
    TABLE_NUMBER_PATTERNS = [
        re.compile(r'^([A-Za-z]+[-\s]\d+)'),        # "A-8" / "B-1"
        re.compile(r'^表\s*(\d+[-\s]\d+)'),          # "表 3-1"
        re.compile(r'^附表\s*([A-Za-z\d\-]+)'),      # "附表 A-8"
        re.compile(r'^Table\s+(\d+)'),                # "Table 1"
        re.compile(r'([A-Z]+-\d+)'),                # "A-8", "B-1" anywhere in text
        re.compile(r'^（\d+）'),                      # "（9）"
    ]

    def __init__(self, clause_nodes: List = None):
        """
        Args:
            clause_nodes: 已提取的条款节点列表（用于关联表格所属章节）
        """
        self._clause_nodes = clause_nodes or []
        self._id_counter = 1
        self._current_clause = ""      # 当前所在条款号

    def extract(self, elements: List) -> List[ExtractedTable]:
        """从元素序列中提取所有表格"""
        tables = []
        self._id_counter = 1
        self._current_clause = ""

        for i, elem in enumerate(elements):
            # 追踪当前所在条款
            if isinstance(elem, ParaElement):
                # 更新当前条款位置
                clause_num = self._detect_clause_number(elem.text)
                if clause_num:
                    self._current_clause = clause_num

            if isinstance(elem, TableElement):
                if elem.row_count == 0:
                    continue

                # 找表格标题（前面的段落）——两层扫描
                title = ""
                table_number = ""
                caption = ""

                # 第一层：紧邻段落作为标题
                for j in range(i - 1, max(i - 4, -1), -1):
                    if j >= 0 and isinstance(elements[j], ParaElement):
                        prev_text = elements[j].text.strip()
                        if len(prev_text) < 100 and prev_text:
                            title = prev_text
                            break

                # 第二层：从标题往前再扫 5 段，找编号（如 "A-8危大工程"）
                title_idx = next((j for j in range(i - 1, max(i - 9, -1), -1)
                                  if isinstance(elements[j], ParaElement) and elements[j].text.strip() == title), i - 1)
                for j in range(title_idx - 1, max(title_idx - 6, -1), -1):
                    if j >= 0 and isinstance(elements[j], ParaElement):
                        candidate = elements[j].text.strip()
                        # 检测类似 "A-8"、"B-1"、"（9）" 的编号
                        num = self._detect_table_number(candidate)
                        if num:
                            table_number = num
                            if not caption:
                                caption = candidate[:100]
                            break

                # 如果编号还没找到，从标题本身检测
                if not table_number:
                    table_number = self._detect_table_number(title)

                # 生成 HTML 预览
                raw_html = self._to_html(elem)

                tables.append(ExtractedTable(
                    id=self._id_counter,
                    table_number=table_number,
                    title=title,
                    caption=caption,
                    chapter_ref=self._current_clause,
                    rows=elem.rows,
                    checkbox_map=elem.checkbox_map,
                    merged_cells=elem.merged_cells,
                    row_count=elem.row_count,
                    col_count=elem.col_count,
                    raw_html=raw_html,
                ))
                self._id_counter += 1

        return tables

    def _detect_table_number(self, text: str) -> str:
        """从文本中检测表格编号"""
        for pattern in self.TABLE_NUMBER_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(0).strip()
        return ""

    def _detect_clause_number(self, text: str) -> Optional[str]:
        """检测段落中的条款号"""
        # §X.Y.Z 模式
        m = re.search(r'(§?\d+\.\d+(?:\.\d+)?)', text)
        if m:
            num = m.group(1)
            if not num.startswith("§"):
                num = "§" + num
            return num
        return None

    def _to_html(self, table: TableElement) -> str:
        """将表格转为 HTML 预览"""
        if not table.rows:
            return ""

        html = '<table border="1" style="border-collapse:collapse">\n'
        for ri, row in enumerate(table.rows):
            html += "<tr>\n"
            for ci, cell in enumerate(row):
                key = f"{ri}_{ci}"
                checked = table.checkbox_map.get(key)
                display = cell
                if checked is True:
                    display = f"[✓] {cell}" if cell else "[✓]"
                elif checked is False:
                    display = f"[ ] {cell}" if cell else "[ ]"
                html += f"<td>{display}</td>\n"
            html += "</tr>\n"
        html += "</table>"
        return html
