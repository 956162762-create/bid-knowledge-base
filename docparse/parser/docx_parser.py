"""
docx 解析器 — 把 Word 文档拆成带类型的元素序列

输出: List[DocElement]
  DocElement = Paragraph | Table
  Paragraph: {type, text, outline_level, formatting}
  Table: {type, rows, caption, checkbox_map}
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from lxml import etree

# XML 命名空间
NSMAP = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'v': 'urn:schemas-microsoft-com:vml',
    'w10': 'urn:schemas-microsoft-com:office:word',
}


@dataclass
class ParaElement:
    """段落元素"""
    element_type: str = "paragraph"
    text: str = ""
    outline_level: int = -1          # -1=正文, 0=Title, 1=Heading1, ...
    style_name: str = ""             # "Heading 1", "Normal" 等
    is_bold: bool = False
    is_red: bool = False
    page_number: Optional[int] = None
    raw_xml: str = ""                # 保留原始 XML（后续深入分析用）


@dataclass
class TableElement:
    """表格元素"""
    element_type: str = "table"
    rows: List[List[str]] = field(default_factory=list)  # [row][col] 纯文本
    checkbox_map: Dict[str, bool] = field(default_factory=dict)  # {"row_col": True/False}
    merged_cells: List[Dict] = field(default_factory=list)  # [{row, col, rowspan, colspan}]
    row_count: int = 0
    col_count: int = 0
    caption: str = ""                 # 表格上方/下方的标题文字
    raw_xml: str = ""


class DocxParser:
    """解析 docx 文档，输出结构化的元素序列"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def parse(self) -> List[Any]:
        """主入口：解析 docx，返回元素列表"""
        from docx import Document as DocxDocument

        doc = DocxDocument(self.file_path)
        body = doc.element.body
        elements = []

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                para = self._parse_paragraph(child)
                if para.text.strip():  # 跳过空段落
                    elements.append(para)

            elif tag == "tbl":
                table = self._parse_table(child)
                if table.row_count > 0:
                    elements.append(table)

        return elements

    def _parse_paragraph(self, para_element) -> ParaElement:
        """解析单个段落"""
        # 获取段落属性
        pPr = para_element.find("w:pPr", NSMAP)

        outline_level = -1
        style_name = ""
        if pPr is not None:
            # 检查 outline level（标题层级）
            pStyle = pPr.find("w:pStyle", NSMAP)
            if pStyle is not None:
                style_name = pStyle.get(f"{{{NSMAP['w']}}}val", "")

            outline_lvl = pPr.find("w:outlineLvl", NSMAP)
            if outline_lvl is not None:
                outline_level = int(outline_lvl.get(f"{{{NSMAP['w']}}}val", "-1"))

        # 提取文本和格式
        text_parts = []
        is_bold = False
        is_red = False

        for run in para_element.findall(".//w:r", NSMAP):
            run_text = ""
            for t in run.findall("w:t", NSMAP):
                if t.text:
                    run_text += t.text

            if not run_text:
                continue

            # 检查格式
            rPr = run.find("w:rPr", NSMAP)
            if rPr is not None:
                # 粗体
                if rPr.find("w:b", NSMAP) is not None:
                    is_bold = True
                # 红色字体
                color = rPr.find("w:color", NSMAP)
                if color is not None:
                    color_val = color.get(f"{{{NSMAP['w']}}}val", "")
                    if color_val.upper() in ("FF0000", "C00000", "RED"):
                        is_red = True

            text_parts.append(run_text)

        raw_xml = etree.tostring(para_element, encoding="unicode")

        return ParaElement(
            text="".join(text_parts),
            outline_level=outline_level,
            style_name=style_name,
            is_bold=is_bold,
            is_red=is_red,
            raw_xml=raw_xml,
        )

    def _parse_table(self, table_element) -> TableElement:
        """解析单个表格——保留完整结构和勾选框状态"""
        rows_xml = table_element.findall(".//w:tr", NSMAP)
        if not rows_xml:
            return TableElement()

        rows = []
        checkbox_map = {}
        merged_cells = []

        for ri, row in enumerate(rows_xml):
            cells = row.findall(".//w:tc", NSMAP)
            row_texts = []
            for ci, cell in enumerate(cells):
                text, is_checked = self._parse_cell(cell)
                row_texts.append(text)

                # 检查是否有勾选框
                if is_checked is not None:
                    checkbox_map[f"{ri}_{ci}"] = is_checked

                # 检查合并单元格
                tcPr = cell.find("w:tcPr", NSMAP)
                if tcPr is not None:
                    gridspan = tcPr.find("w:gridSpan", NSMAP)
                    vmerge = tcPr.find("w:vMerge", NSMAP)
                    if gridspan is not None or vmerge is not None:
                        span = int(gridspan.get(f"{{{NSMAP['w']}}}val", "1")) if gridspan is not None else 1
                        merged_cells.append({
                            "row": ri, "col": ci,
                            "colspan": span,
                            "vmerge": vmerge is not None
                        })

            rows.append(row_texts)

        # 计算实际列数
        max_cols = max(len(r) for r in rows) if rows else 0
        raw_xml = etree.tostring(table_element, encoding="unicode")

        return TableElement(
            rows=rows,
            checkbox_map=checkbox_map,
            merged_cells=merged_cells,
            row_count=len(rows),
            col_count=max_cols,
            raw_xml=raw_xml,
        )

    def _parse_cell(self, cell_element) -> tuple:
        """解析单元格，返回 (text, is_checked)"""
        # 提取纯文本
        text_parts = []
        for node in cell_element.iter():
            if node.tag == f"{{{NSMAP['w']}}}t" and node.text:
                text_parts.append(node.text)

        text = "".join(text_parts).strip()

        # 检测勾选框状态
        xml_str = etree.tostring(cell_element, encoding="unicode")
        has_control = "<w:control" in xml_str
        has_checkbox_name = "CheckBox" in xml_str
        has_t75 = "_x0000_t75" in xml_str  # t75 = 图片 = 打勾

        if has_control and has_checkbox_name and has_t75:
            return (text, True)   # 打勾
        elif has_control and not (has_checkbox_name and has_t75):
            return (text, False)  # 未打勾

        return (text, None)  # 无勾选框
