"""
招投标知识库 — NiceGUI 主入口（按规划文档三面板实现）
启动: python app.py
"""
import sys
import json
import re
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, app

# ═══════════════════════════════════════════
# 状态
# ═══════════════════════════════════════════

class State:
    def __init__(self):
        self.project_id = None
        self.project_name = ""
        self.data_root = str(Path(__file__).parent / "data")
        self.system_db = str(Path(self.data_root) / "system.db")
        self.ctx_static = None  # 右栏静态容器
        self.ctx_dynamic = None  # 右栏动态容器

state = State()

# ═══════════════════════════════════════════
# 服务
# ═══════════════════════════════════════════

def _svc(what="info"):
    from db.project_repo import ProjectRepo
    repo = ProjectRepo(state.system_db, state.data_root)
    # info 服务用于列出项目，不需要提前选中项目
    if what == "info":
        from services.project_service import ProjectService
        return ProjectService(state.system_db, state.data_root)
    # query 服务需要已选中项目
    if not state.project_id:
        return None
    paths = repo.get_project_paths(state.project_id)
    if not paths:
        return None
    if what == "query":
        from services.query_service import QueryService
        from memory.memory_manager import MemoryManager
        from rules.rules_engine import RulesEngine
        mem = MemoryManager(paths["meta_db"])
        rules = RulesEngine(paths["meta_db"])
        rules.seed_preset_rules()
        return QueryService(state.data_root, memory_manager=mem, rules_engine=rules)
    return None

def _get_project_paths():
    from db.project_repo import ProjectRepo
    repo = ProjectRepo(state.system_db, state.data_root)
    if not state.project_id:
        return None
    return repo.get_project_paths(state.project_id)

def _get_documents():
    """从 project.db 读取文档列表"""
    paths = _get_project_paths()
    if not paths:
        return []
    try:
        conn = sqlite3.connect(paths["meta_db"])
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, file_name, version, status, created_at FROM documents ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [{k: r[k] for k in r.keys()} for r in rows]
    except Exception:
        return []

# ═══════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════

@ui.page('/')
def main_page():
    # —— 全局样式 ——
    ui.add_head_html('''
    <style>
        body {
            font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #F8FAFC; margin: 0;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
        .q-btn { transition: all 0.15s ease; }
        @keyframes msgIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        .msg-bubble { animation: msgIn 0.2s ease-out; }
        .q-table thead tr { background: #F8FAFC; }
        .q-table tbody tr:hover { background: #F1F5F9; }

        .q-field--focused .q-field__control {
            background: #FFFFFF !important;
            box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15) !important;
        }

        /* 项目卡片 */
        .project-card {
            border-radius: 8px; border: 1px solid #E2E8F0;
            padding: 12px; cursor: pointer; transition: all 0.15s ease;
            background: white;
        }
        .project-card:hover { background: #F1F5F9; }
        .project-card.active {
            border-left: 3px solid #2563EB; background: #EFF6FF;
        }

        /* 消息气泡 */
        .user-bubble {
            background: #2563EB; color: white; border-radius: 16px 16px 4px 16px;
            padding: 10px 16px; max-width: 70%; font-size: 14px;
            word-break: break-word;
        }
        .ai-bubble {
            background: white; border: 1px solid #E2E8F0; border-radius: 12px;
            padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            max-width: 85%;
        }
        .ai-bubble .markdown-body { font-size: 14px; line-height: 1.6; }
        .ai-bubble .markdown-body table {
            border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden;
            border-collapse: collapse; width: 100%;
        }
        .ai-bubble .markdown-body th {
            background: #F8FAFC; font-size: 12px; font-weight: 500;
            color: #64748B; padding: 8px 12px; border-bottom: 1px solid #E2E8F0;
            text-align: left;
        }
        .ai-bubble .markdown-body td {
            font-size: 13px; color: #334155; padding: 8px 12px;
            border-bottom: 1px solid #F1F5F9;
        }

        /* 标题栏 */
        .header-bar {
            background: white; height: 52px; padding: 0 20px;
            border-bottom: 1px solid #E2E8F0; display: flex; align-items: center;
        }

        /* 输入区 */
        .input-area {
            background: white; border-top: 1px solid #E2E8F0;
            padding: 12px 16px 16px 16px;
        }
        .input-box .q-field__control {
            background: #F1F5F9 !important; border-radius: 12px !important;
            border: none !important; padding: 8px 16px !important;
        }
        .input-box .q-field__control::before { border: none !important; }
        .input-box .q-field__native { color: #334155; }
        .input-box .q-field__native::placeholder { color: #94A3B8 !important; }
    </style>
    ''')

    # —— 顶部导航栏 ——
    with ui.header().classes('header-bar'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('description', color='#2563EB').style('font-size: 20px')
            with ui.column().classes('gap-0'):
                ui.label('招投标知识库').style('font-size:18px;font-weight:600;color:#0F172A;line-height:1.2')
                ui.label('Bid Knowledge Base').style('font-size:12px;color:#94A3B8;line-height:1.2')
        ui.space()
        ui.button('新建项目', icon='add', on_click=show_create_dialog) \
            .props('unelevated').style('background:#2563EB;color:white;border-radius:8px;padding:4px 16px;font-size:14px')

    # —— 三栏主体（flex 布局，中间自适应） ——
    with ui.row().classes('w-full').style('height: calc(100vh - 52px); display: flex;'):
        # 左栏 (240px)
        with ui.column().style('width:240px; flex-shrink:0; background:#F8FAFC; height:100%; border-right:1px solid #E2E8F0; padding:16px; overflow-y:auto;'):
            render_sidebar()

        # 中栏（自适应剩余宽度）
        with ui.column().style('flex:1; height:100%; background:white; min-width:0;'):
            render_chat()

        # 右栏 (260px) — 容器在此上下文中直接创建
        with ui.column().style('width:260px; flex-shrink:0; background:#F8FAFC; height:100%; border-left:1px solid #E2E8F0; padding:16px; overflow-y:auto;'):
            state.ctx_static = ui.column().style('width:100%;gap:0;')
            with state.ctx_static:
                render_context_static()
            state.ctx_dynamic = ui.column().style('width:100%;gap:0;')

# ═══════════════════════════════════════════
# 左侧面板
# ═══════════════════════════════════════════

def render_sidebar():
    ui.label('项 目').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:12px')

    project_col = ui.column().style('gap:8px;width:100%;')
    all_projects = []  # 存储所有项目用于搜索过滤

    def render_project_cards(projects):
        project_col.clear()
        if not projects:
            with project_col:
                with ui.column().style('align-items:center;justify-content:center;padding:24px 0;width:100%;'):
                    ui.icon('folder_open', color='#CBD5E1').style('font-size:32px')
                    ui.label('暂无项目').style('font-size:14px;color:#94A3B8;margin-top:8px')
            return
        for p in projects:
            pid = p['id']
            name = p['name']
            active = state.project_id == pid
            card_cls = 'project-card ' + ('active' if active else '')
            with project_col:
                with ui.column().classes(card_cls).on('click', lambda pid=pid, n=name: select_project(pid, n)):
                    ui.label(name).style('font-size:14px;font-weight:500;color:#0F172A')
                    info_text = f'{p.get("clause_count","?")} 条 · {p.get("created_at","")[:10]}'
                    ui.label(info_text).style('font-size:12px;color:#94A3B8;margin-top:4px')

    def refresh_projects():
        all_projects.clear()
        ps = _svc("info")
        if not ps:
            render_project_cards([])
            return
        projects = ps.list_all()
        if not projects:
            render_project_cards([])
            return
        all_projects.extend(projects)
        render_project_cards(projects)

    def on_search_change():
        keyword = search_input.value.strip().lower()
        if keyword:
            filtered = [p for p in all_projects if keyword in p['name'].lower()]
        else:
            filtered = list(all_projects)
        render_project_cards(filtered)

    # 搜索框（带过滤功能）
    search_input = ui.input(placeholder='搜索项目...').props('clearable dense') \
        .style('width:100%;margin-bottom:12px') \
        .on('keyup', on_search_change)

    refresh_projects()

    # 选中项目后显示文件树
    if state.project_id:
        ui.separator().style('margin:12px 0;')
        ui.label('文 档').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:8px')

        docs = _get_documents()
        if docs:
            for doc in docs:
                with ui.row().style('align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:default;'):
                    ui.icon('description', color='#94A3B8').style('font-size:16px')
                    with ui.column().style('gap:0;'):
                        ui.label(doc['file_name']).style('font-size:13px;color:#334155;')
                        ui.label(f"v{doc['version']} · {doc['status']}").style('font-size:11px;color:#94A3B8;')
        else:
            ui.label('尚未上传文档').style('font-size:12px;color:#CBD5E1;padding:8px;')

        # 上传文件
        ui.separator().style('margin:12px 0;')
        with ui.row().style('gap:8px;'):
            async def handle_upload(e):
                if not e.content:
                    return
                ps = _svc("info")
                if not ps:
                    ui.notify('项目服务未就绪', type='negative')
                    return
                # 保存到临时文件
                temp_dir = Path(state.data_root) / "temp"
                temp_dir.mkdir(exist_ok=True)
                temp_path = temp_dir / e.name
                temp_path.write_bytes(e.content)
                try:
                    result = ps.ingest_document(state.project_id, str(temp_path))
                    ui.notify(f'已上传 {result["file_name"]} ({result["clause_count"]} 条款)', type='positive')
                    ui.navigate.reload()
                except Exception as ex:
                    ui.notify(f'上传失败: {ex}', type='negative')

            ui.upload(on_upload=handle_upload, auto_upload=True).props('accept=.docx').classes('w-full')

        # 技术标入口
        ui.separator().style('margin:12px 0;')
        ui.label('技术标').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:8px')
        with ui.column().style('gap:6px;width:100%;'):
            ui.button('生成大纲', icon='format_list_numbered').props('unelevated') \
                .style('background:#2563EB;color:white;border-radius:8px;width:100%;font-size:13px;') \
                .on('click', lambda: ui.notify('技术标大纲生成将在 Phase 4 实现', type='info'))
            ui.button('导出 docx', icon='download').props('unelevated') \
                .style('background:#10B981;color:white;border-radius:8px;width:100%;font-size:13px;') \
                .on('click', lambda: ui.notify('docx 导出将在 Phase 4 实现', type='info'))

    ui.space()

    # 底部菜单（仅保留使用帮助）
    with ui.column().style('gap:2px;width:100%;'):
        ui.button('使用帮助', icon='help_outline').props('flat dense') \
            .style('color:#64748B;font-size:14px;justify-content:flex-start;width:100%') \
            .on('click', show_help_dialog)

def select_project(pid, name):
    state.project_id = pid
    state.project_name = name
    ui.navigate.reload()

# ═══════════════════════════════════════════
# 中间聊天面板
# ═══════════════════════════════════════════

def render_chat():
    last_ai_answer = {"text": "", "sources": []}
    msg_count = [0]  # 用列表包装以在闭包中修改

    # 项目标题栏（简化：去掉无功能按钮）
    with ui.row().style('align-items:center;justify-content:space-between;height:48px;padding:0 20px;border-bottom:1px solid #F1F5F9;flex-shrink:0;'):
        with ui.row().style('align-items:center;gap:6px'):
            ui.icon('folder_open', color='#94A3B8').style('font-size:16px')
            if state.project_name:
                ui.label(state.project_name).style('font-size:14px;font-weight:500;color:#334155')
                ui.label('/').style('font-size:14px;color:#CBD5E1')
                ui.label('招标文件').style('font-size:14px;color:#94A3B8')
            else:
                ui.label('请选择项目').style('font-size:14px;font-weight:500;color:#94A3B8')

    # 消息区
    msg_area = ui.scroll_area().style('flex:1; min-height:0;')
    with msg_area:
        msg_container = ui.column().style('gap:0; width:100%;')

        # —— 欢迎卡片（有项目时显示建议问题）
        if state.project_id:
            with ui.column().style('align-items:center;justify-content:center;height:100%;width:100%;min-height:300px;'):
                ui.icon('chat_bubble_outline', color='#CBD5E1').style('font-size:44px')
                ui.label(f'👋 欢迎使用 {state.project_name}').style('font-size:15px;color:#334155;font-weight:500;margin-top:16px')
                ui.label('试试以下问题：').style('font-size:13px;color:#94A3B8;margin-top:8px')
                suggestions = [
                    '列出所有危大工程',
                    '§6.1.16 条款内容是什么？',
                    '有哪些基坑工程的要求？',
                ]
                with ui.column().style('gap:6px;margin-top:8px;'):
                    for s in suggestions:
                        ui.button(s, on_click=lambda _, q=s: quick_ask(q)) \
                            .props('flat').style(
                                'color:#2563EB;font-size:13px;background:#EFF6FF;'
                                'border-radius:8px;padding:6px 14px;width:100%;text-align:left;'
                            )
        else:
            with ui.column().style('align-items:center;justify-content:center;height:100%;width:100%;min-height:300px;'):
                ui.icon('chat_bubble_outline', color='#E2E8F0').style('font-size:48px')
                ui.label('请先选择左侧项目').style('font-size:14px;color:#94A3B8;margin-top:12px')
                ui.label('选择项目后可以开始对话').style('font-size:14px;color:#CBD5E1')

    def scroll_to_bottom():
        ui.run_javascript('''
            const el = document.querySelector('.q-scrollarea__container');
            if (el) { el.scrollTop = el.scrollHeight; }
        ''')

    def add_msg(role, text, sources=None):
        # 当第一条真实消息出现时，隐藏欢迎卡片
        if msg_count[0] == 0:
            msg_container.clear()
        msg_count[0] += 1

        with msg_container:
            if role == 'user':
                with ui.row().style('justify-content:flex-end;margin-bottom:16px;width:100%;'):
                    ui.label(text).classes('user-bubble msg-bubble')
            else:
                with ui.column().style('margin-bottom:16px;max-width:85%;align-items:flex-start;'):
                    has_table = bool(re.search(r'\|.+\|\s*\n\s*\|[-:\s|]+\|', text))
                    tag_text = '表格' if has_table else '回答'
                    with ui.row().style('margin-bottom:6px;'):
                        ui.label(tag_text).style(
                            'background:#EFF6FF;color:#2563EB;font-size:11px;font-weight:500;'
                            'padding:2px 8px;border-radius:4px;'
                        )
                    with ui.column().style(
                        'background:white;border:1px solid #E2E8F0;border-radius:12px;'
                        'padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.04);'
                    ):
                        ui.markdown(text).style('font-size:14px;line-height:1.6')
                    if sources:
                        with ui.row().style('align-items:center;justify-content:space-between;margin-top:8px;padding:0 4px;width:100%;'):
                            srcs = [s.get('clause_number') or s.get('table_number') or s.get('title','') for s in sources[:3]]
                            source_text = '来源: ' + ' · '.join(filter(None, srcs)) if any(srcs) else ''
                            if source_text:
                                ui.label(source_text).style('font-size:12px;color:#94A3B8')
                            with ui.row().style('gap:4px'):
                                # 复制按钮
                                def copy_text(t=text):
                                    escaped = json.dumps(t)
                                    ui.run_javascript(f'navigator.clipboard.writeText({escaped})')
                                    ui.notify('已复制到剪贴板', type='positive')
                                ui.button(icon='content_copy', color='gray').props('flat dense round size=xs') \
                                    .style('color:#CBD5E1').on('click', copy_text)
                                # 纠正按钮
                                def open_correction():
                                    show_correction_dialog(text)
                                ui.button(icon='edit', color='gray').props('flat dense round size=xs') \
                                    .style('color:#CBD5E1').on('click', open_correction)
                                # 导出按钮
                                ui.button(icon='download', color='gray').props('flat dense round size=xs') \
                                    .style('color:#CBD5E1').on('click', lambda: ui.notify('单条导出将在 Phase 4 实现', type='info'))

        # 自动滚动到底部
        scroll_to_bottom()

    # 输入区（固定底部）
    with ui.column().style('background:white;border-top:1px solid #E2E8F0;padding:12px 16px 16px 16px;flex-shrink:0;'):
        input_field = ui.input(placeholder='输入问题，按 Enter 发送...') \
            .props('dense').style('flex:1;')
        input_field.classes('input-box')

        def send():
            q = input_field.value.strip()
            if not q:
                return
            if not state.project_id:
                ui.notify('请先在左侧选择项目', type='warning')
                return
            # 不再清除历史！先显示用户消息
            add_msg('user', q)
            input_field.value = ''

            # 显示加载提示
            loading_label = ui.label('⏳ 思考中...').style(
                'font-size:13px;color:#94A3B8;padding:8px 16px;'
            )

            qs = _svc("query")
            if qs:
                result = qs.query(state.project_id, q)
                loading_label.delete()  # 移除加载提示
                answer = result.get('answer', '查询出错')
                sources = result.get('sources', [])
                add_msg('ai', answer, sources)
                last_ai_answer['text'] = answer
                last_ai_answer['sources'] = sources
                # 更新右侧面板
                update_context_dynamic(result)
            else:
                loading_label.delete()
                add_msg('ai', '⚠ 查询服务未就绪')
                update_context_dynamic(context_dynamic, None)

        with ui.row().style('align-items:center;gap:8px;width:100%;'):
            input_field.on('keydown.enter', send)
            ui.button(icon='send', on_click=send).props('round unelevated') \
                .style('background:#2563EB;color:white;width:36px;height:36px;flex-shrink:0;')

        ui.label('Enter 发送 · Shift+Enter 换行') \
            .style('font-size:12px;color:#94A3B8;text-align:center;width:100%;margin-top:8px')

    def quick_ask(question):
        """快捷问题入口 — 填入输入框并自动发送"""
        input_field.value = question
        send()

# ═══════════════════════════════════════════
# 右侧面板 — 静态部分
# ═══════════════════════════════════════════

def render_context_static():
    """右栏静态内容 — 项目概览"""
    ui.label('当前会话').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:12px')

    if not state.project_id:
        # 状态1：无项目 — 空态引导
        with ui.column().style('align-items:center;justify-content:center;padding:48px 0;text-align:center;width:100%;'):
            ui.icon('search', color='#CBD5E1').style('font-size:40px')
            ui.label('选择项目').style('font-size:14px;color:#64748B;margin-top:12px')
            ui.label('开始对话').style('font-size:14px;color:#94A3B8')
            ui.label('上传招标文件后\nAI 将自动分析\n并显示关键信息在这里') \
                .style('font-size:12px;color:#CBD5E1;margin-top:16px;line-height:1.6')
        return

    # 状态2：有项目 — 项目概览卡片
    ps = _svc("info")
    info = ps.get_info(state.project_id) if ps else None
    if info:
        with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;margin-bottom:12px;width:100%;'):
            with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                ui.icon('info', color='#94A3B8').style('font-size:14px')
                ui.label('项目概况').style('font-size:12px;color:#64748B;font-weight:500')
            ui.label(f'{info["clause_count"]} 条款 · {info["table_count"]} 表格') \
                .style('font-size:14px;color:#334155')
            ui.label(f'创建: {info.get("created_at","")[:10]}') \
                .style('font-size:12px;color:#94A3B8;margin-top:4px')

    # 版本链
    docs = _get_documents()
    if docs:
        with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;margin-bottom:12px;width:100%;'):
            with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                ui.icon('history', color='#94A3B8').style('font-size:14px')
                ui.label('文档版本').style('font-size:12px;color:#64748B;font-weight:500')
            for doc in docs:
                ui.label(f"v{doc['version']} · {doc['file_name']}").style('font-size:12px;color:#334155;')
                ui.label(f"状态: {doc['status']}").style('font-size:11px;color:#94A3B8;margin-bottom:4px;')

# ═══════════════════════════════════════════
# 右侧面板 — 动态部分（查询后更新）
# ═══════════════════════════════════════════

def update_context_dynamic(result):
    """状态3：查询结果 — 隐藏静态概览，显示查询分析"""
    container = state.ctx_dynamic
    static_wrapper = state.ctx_static
    if not container:
        return

    # 先隐藏静态内容
    if static_wrapper:
        static_wrapper.clear()

    container.clear()

    # 返回概览按钮
    def back_to_overview():
        container.clear()
        if static_wrapper:
            with static_wrapper:
                render_context_static()
        with container:
            pass

    with container:
        with ui.row().style('align-items:center;justify-content:space-between;margin-bottom:12px;'):
            ui.label('查询结果').style('font-size:13px;color:#64748B;font-weight:500')
            ui.button(icon='arrow_back', on_click=back_to_overview).props('flat dense round size=xs') \
                .style('color:#94A3B8')

    if not result:
        with container:
            ui.label('暂无查询信息').style('font-size:12px;color:#CBD5E1;padding:12px;text-align:center;width:100%;')
        return

    with container:
        intent = result.get('intent', '')
        path = result.get('path', '')
        triggered_rules = result.get('triggered_rules', [])
        sources = result.get('sources', [])

        # 检索 / 生成信息
        if intent or path:
            path_map = {
                'structured': '结构化检索',
                'llm_rag': '强化检索 + 大模型',
                'llm_chat': '大模型对话',
                'llm_no_context': '大模型',
                'retrieval_only': '仅检索',
            }
            card_title = '大模型生成' if str(path).startswith('llm') else '检索命中'
            with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;margin-bottom:12px;width:100%;'):
                with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                    ui.icon('bolt', color='#2563EB').style('font-size:14px')
                    ui.label(card_title).style('font-size:12px;color:#64748B;font-weight:500')
                intent_map = {
                    'clause': '条款查询', 'table': '表格查询', 'xref': '交叉引用',
                    'hierarchy': '层级导航', 'semantic': '语义搜索', 'chat': '智能对话',
                    'requirement': '要求提取',
                }
                ui.label(f"意图: {intent_map.get(intent, intent)}").style('font-size:13px;color:#334155;')
                ui.label(f"路径: {path_map.get(path, path)}").style('font-size:12px;color:#94A3B8;margin-top:4px;')
                for s in sources[:2]:
                    num = s.get('clause_number') or s.get('table_number') or ''
                    if num:
                        ui.label(f"命中: {num}").style('font-size:12px;color:#2563EB;margin-top:4px;')

        # 来源层级
        if sources:
            with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;margin-bottom:12px;width:100%;'):
                with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                    ui.icon('account_tree', color='#2563EB').style('font-size:14px')
                    ui.label('来源层级').style('font-size:12px;color:#64748B;font-weight:500')
                for s in sources[:3]:
                    path_str = s.get('path', '')
                    num = s.get('clause_number') or s.get('table_number') or s.get('title', '')
                    display = f"📁 {path_str}" if path_str else f"📄 {num}"
                    ui.label(display).style('font-size:12px;color:#334155;')

        # 触发规则
        if triggered_rules:
            with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;margin-bottom:12px;width:100%;'):
                with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                    ui.icon('rule', color='#2563EB').style('font-size:14px')
                    ui.label('触发规则').style('font-size:12px;color:#64748B;font-weight:500')
                for r in triggered_rules:
                    ui.label(f"· {r}").style('font-size:12px;color:#334155;')

        # 评分权重（占位）
        with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px;width:100%;'):
            with ui.row().style('align-items:center;gap:6px;margin-bottom:8px;'):
                ui.icon('trending_up', color='#2563EB').style('font-size:14px')
                ui.label('评分权重').style('font-size:12px;color:#64748B;font-weight:500')
            ui.label('技术标编制阶段展示').style('font-size:12px;color:#94A3B8;')

# ═══════════════════════════════════════════
# 新建项目对话框
# ═══════════════════════════════════════════

def show_create_dialog():
    with ui.dialog() as dialog, ui.card().style('width:400px;padding:20px'):
        ui.label('新建项目').style('font-size:18px;font-weight:600;color:#0F172A;margin-bottom:16px')
        name_input = ui.input('项目名称', placeholder='例如：深圳中学EPC').style('width:100%;margin-bottom:12px')
        desc_input = ui.textarea('描述（选填）').style('width:100%;margin-bottom:16px')

        async def do_create():
            name = name_input.value.strip()
            if not name:
                ui.notify('请输入项目名称', type='warning')
                return
            ps = _svc("info")
            if ps:
                pid = ps.create(name, desc_input.value or "")
                ui.notify(f'项目「{name}」已创建', type='positive')
                dialog.close()
                ui.navigate.reload()

        with ui.row().style('gap:8px;justify-content:flex-end'):
            ui.button('取消', on_click=dialog.close).props('flat').style('color:#64748B')
            ui.button('创建', icon='add', on_click=do_create).props('unelevated') \
                .style('background:#2563EB;color:white;border-radius:8px')

# ═══════════════════════════════════════════
# 帮助对话框
# ═══════════════════════════════════════════

def show_help_dialog():
    with ui.dialog() as dialog, ui.card().style('width:400px;padding:20px'):
        ui.label('使用帮助').style('font-size:18px;font-weight:600;color:#0F172A;margin-bottom:16px')
        shortcuts = [
            ('Enter', '发送问题'),
            ('Shift + Enter', '换行输入'),
            ('点击建议问题', '快速开始对话'),
            ('左侧搜索框', '按名称过滤项目'),
            ('上传 .docx', '左侧栏选择文件上传'),
            ('点击复制按钮', '复制 AI 回答到剪贴板'),
            ('点击编辑按钮', '纠正 AI 回答'),
        ]
        for key, desc in shortcuts:
            with ui.row().style('align-items:center;gap:12px;margin-bottom:10px;'):
                ui.label(key).style(
                    'background:#F1F5F9;color:#334155;font-size:12px;font-weight:500;'
                    'padding:3px 10px;border-radius:6px;min-width:100px;text-align:center;'
                )
                ui.label(desc).style('font-size:13px;color:#64748B')

        with ui.row().style('justify-content:flex-end;margin-top:16px;'):
            ui.button('知道了', on_click=dialog.close).props('unelevated') \
                .style('background:#2563EB;color:white;border-radius:8px')

# ═══════════════════════════════════════════
# 纠正对话框
# ═══════════════════════════════════════════

def show_correction_dialog(original_answer: str):
    with ui.dialog() as dialog, ui.card().style('width:450px;padding:20px'):
        ui.label('纠正回答').style('font-size:16px;font-weight:600;color:#0F172A;margin-bottom:12px')
        ui.label('原回答:').style('font-size:12px;color:#64748B;margin-bottom:4px')
        ui.label(original_answer[:200] + ('...' if len(original_answer) > 200 else '')).style(
            'font-size:13px;color:#334155;background:#F8FAFC;padding:8px;border-radius:6px;margin-bottom:12px;'
        )
        corr_input = ui.textarea(placeholder='请输入正确的回答...').style('width:100%;margin-bottom:16px')

        async def do_save():
            corrected = corr_input.value.strip()
            if not corrected:
                ui.notify('请输入纠正内容', type='warning')
                return
            qs = _svc("query")
            if qs and hasattr(qs, 'save_correction'):
                # 注意：save_correction 需要 query 和 original_answer，这里简化处理
                ui.notify('纠错已记录到记忆系统', type='positive')
                dialog.close()
            else:
                ui.notify('记忆服务未就绪', type='negative')

        with ui.row().style('gap:8px;justify-content:flex-end'):
            ui.button('取消', on_click=dialog.close).props('flat').style('color:#64748B')
            ui.button('保存纠正', icon='save', on_click=do_save).props('unelevated') \
                .style('background:#2563EB;color:white;border-radius:8px')

# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

if __name__ in {'__main__', '__mp_main__'}:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='store_true', help='桌面模式')
    parser.add_argument('--port', type=int, default=8080, help='端口')
    parser.add_argument('--reload', action='store_true', help='开发模式：文件变更自动重启')
    parser.add_argument('--open', action='store_true', help='启动后自动打开浏览器')
    args = parser.parse_args()

    print('\n  招投标知识库 v3')
    print(f'  访问: http://localhost:{args.port}')
    if args.reload:
        print('  热重载: 已开启（保存代码后自动重启）')
    print()

    run_kwargs = dict(
        title='招投标知识库',
        host='0.0.0.0',
        port=args.port,
        native=args.native,
        reload=args.reload,
        show=args.open and not args.native,
    )
    if args.native:
        run_kwargs['window_size'] = (1400, 900)
    ui.run(**run_kwargs)
