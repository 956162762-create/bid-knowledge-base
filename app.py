"""
招投标知识库 — NiceGUI 主入口（白蓝风格 v2）
启动: python app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, app

# ═══════════════════════════════════════════
# 全局样式
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
# 状态
# ═══════════════════════════════════════════

class State:
    def __init__(self):
        self.project_id = None
        self.project_name = ""
        self.data_root = str(Path(__file__).parent / "data")
        self.system_db = str(Path(self.data_root) / "system.db")

state = State()

# ═══════════════════════════════════════════
# 服务懒加载
# ═══════════════════════════════════════════

def _svc(what):
    return get_service(what)

def get_service(what="query"):
    from db.project_repo import ProjectRepo
    repo = ProjectRepo(state.system_db, state.data_root)
    if not state.project_id:
        return None
    paths = repo.get_project_paths(state.project_id)
    if not paths:
        return None
    if what == "info":
        from services.project_service import ProjectService
        return ProjectService(state.system_db, state.data_root)
    if what == "query":
        from services.query_service import QueryService
        from memory.memory_manager import MemoryManager
        from rules.rules_engine import RulesEngine
        mem = MemoryManager(paths["meta_db"])
        rules = RulesEngine(paths["meta_db"])
        rules.seed_preset_rules()
        return QueryService(state.data_root, memory_manager=mem, rules_engine=rules)

# ═══════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════

@ui.page('/')
def main_page():
    ui.add_head_html('''
    <style>
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
        .q-field--focused .q-field__control {
            box-shadow: 0 0 0 2px rgba(37,99,235,0.15) !important;
        }
        .q-btn { transition: all 0.15s ease; }
        @keyframes messageIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        .msg-bubble { animation: messageIn 0.2s ease-out; }
        .q-table thead tr { background: #F8FAFC; }
        .q-table tbody tr:hover { background: #F1F5F9; }
        body { font-family: -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background: #F8FAFC; }
    </style>
    ''')

    # ── 顶部导航栏 ──
    with ui.header().classes('bg-white border-b border-gray-200 h-[52px]').style('padding: 0 20px'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('description', color='#2563EB').style('font-size: 20px')
            with ui.column().classes('gap-0'):
                ui.label('招投标知识库').classes('text-lg font-semibold text-gray-900 leading-tight')
                ui.label('Bid Knowledge Base').classes('text-xs text-gray-400 leading-tight')
        ui.space()
        ui.button('新建项目', icon='add', on_click=show_create_dialog) \
            .props('unelevated').classes('rounded-lg px-4 py-1.5 text-sm bg-primary text-white')

    # ── 三栏主体 ──
    with ui.splitter(limits=(200, 280)).classes('w-full') as splitter:
        with splitter.before:
            render_sidebar()
        with splitter.after:
            with ui.splitter(limits=(300, 400)).classes('w-full') as right_splitter:
                with right_splitter.before:
                    render_chat()
                with right_splitter.after:
                    render_context()

# ═══════════════════════════════════════════
# 左侧面板
# ═══════════════════════════════════════════

def render_sidebar():
    with ui.column().classes('w-[240px] bg-gray-50 h-full border-r border-gray-200 p-4'):
        ui.label('项目').classes('text-sm text-gray-500 font-medium mb-3')
        ui.input(placeholder='搜索项目...').props('clearable dense').classes('w-full mb-3')

        project_col = ui.column().classes('gap-2 w-full')

        def refresh():
            project_col.clear()
            ps = _svc("info")
            if not ps:
                with project_col:
                    ui.label('暂无项目').classes('text-sm text-gray-400 p-3')
                return
            for p in ps.list_all():
                pid = p['id']
                name = p['name']
                active = state.project_id == pid
                cls = 'rounded-lg border p-3 cursor-pointer transition-all '
                cls += 'border-l-[3px] border-l-primary bg-blue-50 border-gray-100' if active \
                  else 'bg-white border-gray-100 hover:bg-gray-50'
                with project_col:
                    with ui.column().classes(cls).on('click', lambda pid=pid, n=name: select_project(pid, n)):
                        ui.label(name).classes('text-sm font-medium text-gray-900')
                        ui.label(f'{p.get("clause_count","?")} 条 · {p.get("created_at","")[:10]}') \
                            .classes('text-xs text-gray-400 mt-1')
        refresh()

        ui.space()
        with ui.column().classes('gap-1'):
            ui.button('系统设置', icon='settings').props('flat dense') \
                .classes('text-gray-500 text-sm justify-start w-full')
            ui.button('使用帮助', icon='help_outline').props('flat dense') \
                .classes('text-gray-500 text-sm justify-start w-full')

def select_project(pid, name):
    state.project_id = pid
    state.project_name = name
    ui.navigate.reload()

# ═══════════════════════════════════════════
# 中间聊天面板
# ═══════════════════════════════════════════

def render_chat():
    with ui.column().classes('flex-1 h-full bg-white'):
        # 项目标题栏
        with ui.row().classes('items-center justify-between h-12 px-5 border-b border-gray-100'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('folder_open', color='#94A3B8').style('font-size: 16px')
                name = state.project_name or '选择项目'
                ui.label(name).classes('text-sm font-medium text-gray-700')
            with ui.row().classes('gap-2'):
                ui.button('上传文件', icon='attach_file').props('flat dense').classes('text-gray-500 text-sm')

        # 消息区域
        msg_area = ui.scroll_area().classes('flex-1 p-5').style('min-height: 0')
        msg_container = ui.column().classes('gap-0')

        def add_msg(role, text, sources=None):
            with msg_container:
                if role == 'user':
                    with ui.row().classes('justify-end mb-3'):
                        ui.label(text).classes(
                            'bg-primary text-white rounded-2xl rounded-tr-sm px-4 py-2.5 '
                            'text-sm max-w-[70%] msg-bubble'
                        )
                else:
                    with ui.column().classes('mb-3 max-w-[90%] msg-bubble'):
                        # 检测是否是表格
                        if '|' in text and '\n|-' in text:
                            with ui.column().classes('bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden p-4'):
                                ui.markdown(text)
                        else:
                            with ui.column().classes('bg-white border border-gray-100 rounded-xl shadow-sm p-4'):
                                ui.markdown(text)
                        if sources:
                            with ui.row().classes('items-center justify-between mt-2 px-1'):
                                src_tags = [s.get('clause_number') or s.get('table_number') or s.get('title','') for s in sources[:3]]
                                ui.label('来源：' + ' · '.join(filter(None, src_tags))).classes('text-xs text-gray-400')
                                ui.button(icon='content_copy', color='gray').props('flat dense round').classes('text-gray-400')

        # 输入区（固定底部）
        with ui.column().classes('w-full bg-white border-t border-gray-100 pt-3 pb-4 px-4'):
            input_field = ui.input(placeholder='输入问题，按 Enter 发送...') \
                .classes('flex-1 bg-gray-50 border-0 rounded-xl px-4 py-3 text-sm').props('dense')

            def send():
                q = input_field.value.strip()
                if not q:
                    return
                if not state.project_id:
                    ui.notify('请先在左侧选择项目', type='warning')
                    return
                add_msg('user', q)
                input_field.value = ''
                qs = _svc("query")
                if qs:
                    result = qs.query(state.project_id, q)
                    add_msg('ai', result.get('answer', '查询出错'), result.get('sources'))
                else:
                    add_msg('ai', '⚠ 查询服务未就绪')

            with ui.row().classes('items-center gap-2 w-full'):
                input_field.on('keydown.enter', send)
                ui.button(icon='send', on_click=send).props('round unelevated').classes('w-9 h-9 bg-primary text-white')

            ui.label('Enter 发送 · 项目选择后即可提问').classes('text-xs text-gray-300 text-center w-full mt-2')

# ═══════════════════════════════════════════
# 右侧面板
# ═══════════════════════════════════════════

def render_context():
    with ui.column().classes('w-[260px] bg-gray-50 h-full border-l border-gray-200 p-4'):
        ui.label('当前会话').classes('text-sm text-gray-500 font-medium mb-3')

        if not state.project_id:
            with ui.column().classes('items-center justify-center py-12 text-center'):
                ui.icon('search', color='#CBD5E1').style('font-size: 40px')
                ui.label('选择项目').classes('text-sm text-gray-500 mt-3')
                ui.label('开始对话').classes('text-sm text-gray-400')
                ui.label('上传招标文件后，AI 将自动分析并显示关键信息').classes('text-xs text-gray-300 mt-4')
            return

        ps = _svc("info")
        info = ps.get_info(state.project_id) if ps else None
        if not info:
            return

        # 信息卡片
        with ui.column().classes('bg-white rounded-lg border border-gray-100 p-3 mb-3'):
            ui.label('项目信息').classes('text-xs text-gray-500 mb-2')
            ui.label(f'{info["clause_count"]} 条款 · {info["table_count"]} 表格') \
                .classes('text-sm text-gray-700')
            ui.label(f'创建: {info.get("created_at","")[:10]}').classes('text-xs text-gray-400 mt-1')

# ═══════════════════════════════════════════
# 新建项目对话框
# ═══════════════════════════════════════════

def show_create_dialog():
    with ui.dialog() as dialog, ui.card().classes('p-5 w-[400px]'):
        ui.label('新建项目').classes('text-lg font-semibold text-gray-900 mb-4')
        name_input = ui.input('项目名称', placeholder='例如：深圳中学EPC').classes('w-full mb-3')
        desc_input = ui.textarea('描述（选填）').classes('w-full mb-4')

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

        with ui.row().classes('gap-2 justify-end'):
            ui.button('取消', on_click=dialog.close).props('flat').classes('text-gray-500')
            ui.button('创建', icon='add', on_click=do_create).props('unelevated').classes('bg-primary text-white rounded-lg')

# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

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
        window_size=(1400, 900),
    )
