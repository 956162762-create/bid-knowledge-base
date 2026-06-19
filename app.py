"""
招投标知识库 — NiceGUI 主入口
启动: python app.py
桌面模式: python app.py --native
"""
import sys
import os
from pathlib import Path

# 确保能找到项目模块
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, app

# 全局状态
class AppState:
    def __init__(self):
        self.current_project_id = None
        self.current_project_name = ""
        self.messages = []            # [{role, content, sources, time}]
        self.data_root = str(Path(__file__).parent / "data")
        self.system_db = str(Path(self.data_root) / "system.db")

state = AppState()

# 懒加载服务
def get_query_service():
    from services.query_service import QueryService
    from memory.memory_manager import MemoryManager
    from rules.rules_engine import RulesEngine

    if not state.current_project_id:
        return None

    paths = get_project_paths()
    if not paths:
        return None

    memory = MemoryManager(paths["meta_db"])
    rules = RulesEngine(paths["meta_db"])
    rules.seed_preset_rules()
    return QueryService(state.data_root, memory_manager=memory, rules_engine=rules)

def get_project_service():
    from services.project_service import ProjectService
    return ProjectService(state.system_db, state.data_root)

def get_project_paths():
    from db.project_repo import ProjectRepo
    repo = ProjectRepo(state.system_db, state.data_root)
    return repo.get_project_paths(state.current_project_id)

# ─── 主布局：三面板 ───

@ui.page('/')
def main_page():
    # 全局样式
    ui.add_head_html('''
    <style>
        body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
        .chat-msg { padding: 8px 12px; margin: 4px 0; border-radius: 8px; }
        .chat-user { background: #1a3a5c; color: #e0e0e0; }
        .chat-ai { background: #1e2130; color: #d4d6dc; }
        .source-tag { font-size: 0.8em; color: #5b8def; cursor: pointer; }
    </style>
    ''')

    with ui.header().classes('bg-dark text-white'):
        ui.label('📋 招投标知识库').classes('text-h5')
        ui.space()
        ui.button('新建项目', icon='add', on_click=lambda: create_dialog.open()).props('flat')

    with ui.splitter(limits=(240, 350)).classes('w-full h-full') as splitter:
        # ── 左侧：项目面板 ──
        with splitter.before:
            render_sidebar()

        # ── 中央：聊天面板 ──
        with splitter.after:
            with ui.splitter(limits=(400, 500)).classes('w-full') as right_splitter:
                with right_splitter.before:
                    render_chat()
                with right_splitter.after:
                    render_context()

# ─── 左侧面板 ───

def render_sidebar():
    def on_project_select(project_id, name):
        state.current_project_id = project_id
        state.current_project_name = name
        project_label.set_text(f'📁 {name}')
        load_context()

    with ui.column().classes('p-4 gap-2 w-full'):
        ui.label('📁 项目列表').classes('text-h6 text-bold')
        project_list = ui.column().classes('gap-1 w-full')
        project_label = ui.label('未选择项目').classes('text-grey')

        # 刷新项目列表
        def refresh_projects():
            project_list.clear()
            ps = get_project_service()
            for p in ps.list_all():
                pid = p['id']
                with project_list:
                    ui.button(p['name'], on_click=lambda pid=pid, name=p['name']: on_project_select(pid, name)) \
                        .props('flat dense align=left').classes('w-full')

        refresh_projects()
        ui.button('🔄 刷新', on_click=refresh_projects).props('flat dense').classes('mt-2')

# ─── 中央聊天面板 ───

def render_chat():
    chat_container = ui.column().classes('p-4 gap-2')
    chat_display = ui.column().classes('overflow-y-auto flex-grow')

    def add_message(role, content, sources=None):
        state.messages.append({"role": role, "content": content, "sources": sources or []})
        with chat_display:
            css_class = 'chat-user' if role == 'user' else 'chat-ai'
            with ui.card().classes(f'q-pa-sm {css_class}'):
                prefix = '👤' if role == 'user' else '🤖'
                ui.label(f'{prefix} {content}').classes('text-body1')
                if sources:
                    for s in sources[:3]:
                        src_text = s.get('clause_number') or s.get('table_number') or s.get('title', '')
                        ui.label(f'📎 {src_text}').classes('source-tag')

    def send_message():
        query_text = input_field.value.strip()
        if not query_text:
            return
        if not state.current_project_id:
            ui.notify('请先选择项目', type='warning')
            return

        add_message('user', query_text)
        input_field.value = ''

        qs = get_query_service()
        if qs:
            result = qs.query(state.current_project_id, query_text)
            add_message('ai', result.get('answer', '查询出错'),
                       sources=result.get('sources', []))
            load_context()
        else:
            add_message('ai', '⚠ 查询服务未就绪，请确认项目已选择并已摄入文档')

    with chat_container:
        ui.label(f'💬 问答').classes('text-h6 text-bold').bind_text_from(state, 'current_project_name', backward=lambda n: f'💬 {n}' if n else '💬 问答')
        chat_display
        with ui.row().classes('w-full items-center gap-2'):
            input_field = ui.input(placeholder='输入问题...').classes('flex-grow') \
                .on('keydown.enter', send_message)
            ui.button('发送', icon='send', on_click=send_message).props('flat')

# ─── 右侧上下文面板 ───

def render_context():
    context_col = ui.column().classes('p-4 gap-2')

    def load_context():
        context_col.clear()
        if not state.current_project_id:
            with context_col:
                ui.label('📊 上下文').classes('text-h6 text-bold')
                ui.label('请先选择项目').classes('text-grey')
            return

        ps = get_project_service()
        info = ps.get_info(state.current_project_id)

        with context_col:
            ui.label('📊 项目概况').classes('text-h6 text-bold')
            if info:
                ui.label(f'条款节点: {info[\"clause_count\"]}').classes('text-body2')
                ui.label(f'表格数量: {info[\"table_count\"]}').classes('text-body2')
                ui.label(f'创建时间: {info[\"created_at\"][:10]}').classes('text-body2')

            ui.separator()
            ui.label('📋 规则状态').classes('text-h6 text-bold')
            try:
                if state.current_project_id:
                    paths = get_project_paths()
                    if paths:
                        from rules.rules_engine import RulesEngine
                        rules = RulesEngine(paths["meta_db"])
                        rules_list = rules.list_rules()
                        for r in rules_list[:5]:
                            ui.label(f'· {r[\"name\"]}').classes('text-caption')
            except:
                ui.label('规则未加载').classes('text-grey')

    load_context()

# ─── 新建项目对话框 ───

@ui.dialog()
def create_dialog():
    name_input = ui.input('项目名称', placeholder='例如：深圳中学EPC').classes('w-full')
    desc_input = ui.textarea('描述').classes('w-full')

    async def create():
        name = name_input.value.strip()
        if not name:
            ui.notify('请输入项目名称', type='warning')
            return
        ps = get_project_service()
        pid = ps.create(name, desc_input.value)
        ui.notify(f'项目 {name} 已创建 (id={pid})', type='positive')
        create_dialog.close()
        # 刷新界面
        ui.navigate.reload()

    with ui.card().classes('p-4'):
        ui.label('新建项目').classes('text-h6')
        name_input
        desc_input
        with ui.row().classes('gap-2 justify-end'):
            ui.button('取消', on_click=create_dialog.close).props('flat')
            ui.button('创建', icon='add', on_click=create).props('flat')

# ─── 启动 ───

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='store_true', help='桌面模式')
    parser.add_argument('--port', type=int, default=8080, help='端口')
    args = parser.parse_args()

    print('招投标知识库 v3')
    print(f'访问: http://localhost:{args.port}')

    ui.run(
        title='招投标知识库',
        host='0.0.0.0',
        port=args.port,
        native=args.native,
        reload=False,
        window_size=(1400, 900) if args.native else None,
    )
