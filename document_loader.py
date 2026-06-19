"""
文档加载器 - 针对招投标文件优化
支持: .docx (含表格结构保留、勾选框识别) / .md / .txt
"""
import os
from pathlib import Path
from typing import List, Tuple, Optional
from lxml import etree


class DocumentLoader:
    """加载各类文档文件，返回原始文本内容"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"文档不存在: {file_path}")
        # 当前所在卷/篇/章（用于来源标注）
        self._current_volume = ""
        self._current_chapter = ""
        self._current_section = ""

    def load(self) -> str:
        """根据文件扩展名选择对应的加载方法"""
        ext = self.file_path.suffix.lower()
        if ext == ".docx":
            return self._load_docx()
        else:
            return self._load_text()

    def load_with_source(self) -> List[dict]:
        """
        加载文档并返回带来源标注的段落列表
        Returns: [{"text": ..., "source": "第一卷·第1篇·投标人须知"}, ...]
        """
        ext = self.file_path.suffix.lower()
        if ext == ".docx":
            return self._load_docx_with_source()
        else:
            content = self._load_text()
            return [{"text": content, "source": str(self.file_path)}]

    # ===== 纯文本加载 =====

    def _load_text(self) -> str:
        for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(self.file_path, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        with open(self.file_path, "r") as f:
            return f.read()

    # ===== DOCX 加载（段落 + 表格）=====

    def _load_docx(self) -> str:
        """加载 Word 文档，保留表格结构和勾选状态"""
        parts = self._parse_docx_elements()
        return "\n\n".join(parts)

    def _load_docx_with_source(self) -> List[dict]:
        """加载 Word 文档，每段带来源标注"""
        from docx import Document as DocxDocument
        doc = DocxDocument(str(self.file_path))
        body = doc.element.body

        results = []
        volume = ""
        chapter = ""
        section = ""
        source = str(self.file_path.name)

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                text = self._get_para_text(child).strip()
                if not text:
                    continue

                # 追踪文档结构
                parsed = self._parse_heading(text)
                if parsed:
                    level, heading_text = parsed
                    if level == 1:
                        volume = heading_text
                    elif level == 2:
                        chapter = heading_text
                        section = ""
                    elif level == 3:
                        section = heading_text

                # 组装来源
                source_parts = [source]
                if volume:
                    source_parts.append(volume)
                if chapter:
                    source_parts.append(chapter)
                if section:
                    source_parts.append(section)

                results.append({
                    "text": text,
                    "source": " · ".join(source_parts),
                })

            elif tag == "tbl":
                table_text = self._extract_table(child)
                if table_text.strip():
                    source_parts = [source]
                    if volume:
                        source_parts.append(volume)
                    if chapter:
                        source_parts.append(chapter)
                    if section:
                        source_parts.append(section)
                    results.append({
                        "text": table_text,
                        "source": " · ".join(source_parts),
                    })

        return results

    def _parse_docx_elements(self) -> List[str]:
        """按元素顺序提取文档内容，段落和表格分别处理"""
        from docx import Document as DocxDocument
        doc = DocxDocument(str(self.file_path))
        body = doc.element.body

        parts = []
        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                text = self._get_para_text(child).strip()
                if text:
                    parts.append(text)

            elif tag == "tbl":
                table_text = self._extract_table(child)
                if table_text.strip():
                    parts.append(table_text)

        return parts

    def _get_para_text(self, para_element) -> str:
        """获取段落纯文本"""
        texts = []
        for node in para_element.iter():
            if node.text:
                texts.append(node.text)
        return "".join(texts)

    def _parse_heading(self, text: str) -> Optional[Tuple[int, str]]:
        """识别文档结构标题，返回 (层级, 标题文本)"""
        # 卷
        for prefix in ["第", "第一卷", "第二卷", "第三卷", "第四卷",
                       "第五卷", "第六卷", "第七卷", "第八卷"]:
            if text.startswith(prefix) and ("卷" in text[:10]):
                return (1, text[:60])

        # 篇
        for prefix in ["第1篇", "第2篇", "第3篇", "第4篇", "第5篇",
                       "第6篇", "第7篇", "第8篇",
                       "第一篇", "第二篇", "第三篇", "第四篇"]:
            if text.startswith(prefix):
                return (2, text[:60])

        # 章/节 (如 §6.1, 6.1.16)
        import re
        if re.match(r'^\d+\.\d+', text):
            return (3, text[:60])
        if re.match(r'^第[一二三四五六七八九十\d]+章', text):
            return (3, text[:60])

        return None

    # ===== 表格提取（核心改进）=====

    def _extract_table(self, table_element) -> str:
        """
        提取表格为结构化文本。
        - 保留行列关系（每行一行，列用 | 分隔）
        - 识别 ActiveX 勾选框 → 转为 [✓] 或 [ ]
        """
        nsmap = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        }

        rows = table_element.findall('.//w:tr', nsmap)
        if not rows:
            return ""

        table_lines = []
        for row in rows:
            cells = row.findall('.//w:tc', nsmap)
            cell_texts = []
            for cell in cells:
                text = self._get_cell_text_with_checkboxes(cell)
                cell_texts.append(text)
            table_lines.append(" | ".join(cell_texts))

        return "\n".join(table_lines)

    def _get_cell_text_with_checkboxes(self, cell_element) -> str:
        """
        提取单元格文本，同时将勾选框转为文字标记。

        判断逻辑:
        - 有 w:control 且 name 含 "CheckBox" 且 shape 类型为 t75（图片）→ [✓]
        - 仅有 w:control 但 shape 为 t201（文本框）→ [ ]
        - 无控件 → 返回纯文本
        """
        xml_str = etree.tostring(cell_element, encoding="unicode")
        cell_text = self._get_para_text(cell_element).strip()

        has_control = "<w:control" in xml_str
        has_t75 = "_x0000_t75" in xml_str
        has_checkbox_name = "CheckBox" in xml_str

        if has_control and has_checkbox_name and has_t75:
            # 打勾的复选框
            return f"[✓] {cell_text}" if cell_text else "[✓]"
        elif has_control and not (has_checkbox_name and has_t75):
            # 未打勾的复选框
            return f"[ ] {cell_text}" if cell_text else "[ ]"
        else:
            return cell_text

    # ===== 批量加载 =====

    @staticmethod
    def load_directory(dir_path: str, extensions: List[str] = None) -> List[dict]:
        """批量加载目录中的文档"""
        if extensions is None:
            extensions = [".md", ".txt", ".docx"]

        documents = []
        dir_path = Path(dir_path)

        for ext in extensions:
            for file_path in dir_path.glob(f"**/*{ext}"):
                try:
                    loader = DocumentLoader(str(file_path))
                    content = loader.load()
                    documents.append({
                        "path": str(file_path),
                        "content": content,
                    })
                    print(f"  ✓ 已加载: {file_path.name}")
                except Exception as e:
                    print(f"  ✗ 加载失败 {file_path.name}: {e}")

        return documents
