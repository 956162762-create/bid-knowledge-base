"""
招投标知识库 — NiceGUI 主入口（白蓝风格 v2 · Quasar 原生适配）
启动: python app.py
"""
import sys
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

state = State()

# ═══════════════════════════════════════════
# 服务
# ═══════════════════════════════════════════

def _svc(what="info"):
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

        /* 面板背景 */
        .sidebar-bg { background: #F8FAFC; }
        .panel-white { background: #FFFFFF; }

        /* 选中项目卡片 */
        .project-card {
            border-radius: 8px; border: 1px solid #E2E8F0;
            padding: 12px; cursor: pointer; transition: all 0.15s ease;
        }
        .project-card:hover { background: #F1F5F9; }
        .project-card.active {
            border-left: 3px solid #2563EB; background: #EFF6FF;
        }

        /* 消息气泡 */
        .user-bubble {
            background: #2563EB; color: white; border-radius: 16px 16px 4px 16px;
            padding: 10px 16px; max-width: 70%; font-size: 14px;
        }
        .ai-bubble {
            background: white; border: 1px solid #E2E8F0; border-radius: 12px;
            padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
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

    # —— 三栏主体 ——
    with ui.splitter(limits=(200, 280)).style('width:100%') as splitter:
        with splitter.before:
            render_sidebar()
        with splitter.after:
            with ui.splitter(limits=(300, 400)).style('width:100%') as right_splitter:
                with right_splitter.before:
                    render_chat()
                with right_splitter.after:
                    render_context()

# ═══════════════════════════════════════════
# 左侧面板
# ═══════════════════════════════════════════

def render_sidebar():
    with ui.column().style('width:240px;background:#F8FAFC;height:100%;border-right:1px solid #E2E8F0;padding:16px'):
        ui.label('项 目').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:12px')
        ui.input(placeholder='搜索...').props('clearable dense').style('width:100%;margin-bottom:12px')

        project_col = ui.column().style('gap:8px;width:100%')

        def refresh():
            project_col.clear()
            ps = _svc("info")
            if not ps:
                with project_col:
                    ui.label('暂无项目').style('font-size:14px;color:#94A3B8;padding:12px')
                return
            for p in ps.list_all():
                pid = p['id']
                name = p['name']
                active = state.project_id == pid
                card_style = (
                    'border-radius:8px;border:1px solid #E2E8F0;padding:12px;cursor:pointer;'
                )
                if active:
                    card_style += 'border-left:3px solid #2563EB;background:#EFF6FF;'
                else:
                    card_style += 'background:white;'

                with project_col:
                    with ui.column().style(card_style).on('click', lambda pid=pid, n=name: select_project(pid, n)):
                        ui.label(name).style('font-size:14px;font-weight:500;color:#0F172A')
                        ui.label(f'{p.get("clause_count","?")} 条 · {p.get("created_at","")[:10]}') \
                            .style('font-size:12px;color:#94A3B8;margin-top:4px')
        refresh()

        ui.space()
        with ui.column().style('gap:2px'):
            ui.button('系统设置', icon='settings').props('flat dense') \
                .style('color:#64748B;font-size:14px;justify-content:flex-start;width:100%')
            ui.button('使用帮助', icon='help').props('flat dense') \
                .style('color:#64748B;font-size:14px;justify-content:flex-start;width:100%')

def select_project(pid, name):
    state.project_id = pid
    state.project_name = name
    ui.navigate.reload()

# ═══════════════════════════════════════════
# 中间聊天面板
# ═══════════════════════════════════════════

def render_chat():
    with ui.column().style('flex:1;height:100%;background:white'):
        # 标题栏
        with ui.row().style('align-items:center;justify-content:space-between;height:48px;padding:0 20px;border-bottom:1px solid #F1F5F9'):
            with ui.row().style('align-items:center;gap:8px'):
                ui.icon('folder_open', color='#94A3B8').style('font-size:16px')
                ui.label(state.project_name or '选择项目').style('font-size:14px;font-weight:500;color:#334155')

        # 消息区
        msg_area = ui.scroll_area().style('flex:1;padding:20px;min-height:0')
        msg_container = ui.column().style('gap:0')

        def add_msg(role, text, sources=None):
            with msg_container:
                if role == 'user':
                    with ui.row().style('justify-content:flex-end;margin-bottom:12px'):
                        ui.label(text).style(
                            'background:#2563EB;color:white;border-radius:16px 16px 4px 16px;'
                            'padding:10px 16px;max-width:70%;font-size:14px;animation:msgIn .2s ease-out'
                        )
                else:
                    with ui.column().style('margin-bottom:12px;max-width:90%;animation:msgIn .2s ease-out'):
                        has_table = '|' in text and '\n|-' in text
                        with ui.column().style(
                            'background:white;border:1px solid #E2E8F0;border-radius:12px;'
                            'padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)'
                        ):
                            if has_table:
                                ui.markdown(text).style('font-size:14px')
                            else:
                                ui.markdown(text).style('font-size:14px')
                        if sources:
                            with ui.row().style('align-items:center;justify-content:space-between;margin-top:8px;padding:0 4px'):
                                srcs = [s.get('clause_number') or s.get('table_number') or s.get('title','') for s in sources[:3]]
                                ui.label('来源: ' + ' · '.join(filter(None, srcs))) \
                                    .style('font-size:12px;color:#94A3B8')
                                ui.button(icon='content_copy').props('flat dense round size=xs').style('color:#94A3B8')

        # 输入区（固定底部）
        with ui.column().style('background:white;border-top:1px solid #E2E8F0;padding:12px 16px 16px 16px'):
            input_field = ui.input(placeholder='输入问题，按 Enter 发送...') \
                .props('dense').style('width:100%')

            def send():
                q = input_field.value.strip()
                if not q: return
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

            with ui.row().style('align-items:center;gap:8px;width:100%'):
                input_field.on('keydown.enter', send)
                ui.button(icon='send', on_click=send).props('round unelevated') \
                    .style('background:#2563EB;color:white;width:36px;height:36px')

            ui.label('Enter 发送 · 选择项目后即可提问') \
                .style('font-size:12px;color:#CBD5E1;text-align:center;width:100%;margin-top:8px')

# ═══════════════════════════════════════════
# 右侧面板
# ═══════════════════════════════════════════

def render_context():
    with ui.column().style('width:260px;background:#F8FAFC;height:100%;border-left:1px solid #E2E8F0;padding:16px'):
        ui.label('当前会话').style('font-size:13px;color:#64748B;font-weight:500;margin-bottom:12px')

        if not state.project_id:
            with ui.column().style('align-items:center;justify-content:center;padding:48px 0;text-align:center'):
                ui.icon('search', color='#CBD5E1').style('font-size:40px')
                ui.label('选择项目').style('font-size:14px;color:#64748B;margin-top:12px')
                ui.label('开始对话').style('font-size:14px;color:#94A3B8')
                ui.label('上传招标文件后\nAI 将自动分析\n并显示关键信息在这里') \
                    .style('font-size:12px;color:#CBD5E1;margin-top:16px;line-height:1.6')
            return

        ps = _svc("info")
        info = ps.get_info(state.project_id) if ps else None
        if info:
            with ui.card().style('background:white;border-radius:8px;border:1px solid #E2E8F0;padding:12px'):
                ui.label('项目信息').style('font-size:12px;color:#64748B;margin-bottom:8px')
                ui.label(f'{info["clause_count"]} 条款 · {info["table_count"]} 表格') \
                    .style('font-size:14px;color:#334155')
                ui.label(f'创建: {info.get("created_at","")[:10]}') \
                    .style('font-size:12px;color:#94A3B8;margin-top:4px')

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
