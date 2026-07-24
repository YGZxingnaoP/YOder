"""
agent_worker.py - 思维链模式的 QThread 工作线程
"""
from PySide6.QtCore import QObject, Slot, Signal

from .agent_core import run_agent_pipeline


class AgentWorker(QObject):
    """
    在后台线程中运行 Agent 流程。

    信号:
    - progress(status: str, tasklist_json: str)  更新进度条
    - stream(type: str, content: str)            流式输出（思考+最终内容）
    - finished()                                 完成
    - error(msg: str)                            出错
    """
    progress = Signal(str, str)
    stream = Signal(str, str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, client, model, platform, user_message,
                 selected_files, root_path="", thinking_level="high",
                 history=None, max_tokens=65536):
        super().__init__()
        self.client = client
        self.model = model
        self.platform = platform
        self.user_message = user_message
        self.selected_files = selected_files
        self.root_path = root_path
        self.thinking_level = thinking_level
        self.history = history or []
        self.max_tokens = max_tokens

    @Slot()
    def run(self):
        import json
        try:
            def progress_cb(status, tasks):
                self.progress.emit(status, json.dumps(tasks, ensure_ascii=False))

            def stream_cb(type_, content):
                self.stream.emit(type_, content)

            def thinking_cb(content):
                self.stream.emit("thinking", content)

            run_agent_pipeline(
                client=self.client,
                model=self.model,
                platform=self.platform,
                user_message=self.user_message,
                selected_files=self.selected_files,
                root_path=self.root_path,
                thinking_level=self.thinking_level,
                progress_callback=progress_cb,
                stream_callback=stream_cb,
                thinking_callback=thinking_cb,
                history=self.history,
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
            # 注意：不再调用 self.finished.emit()，避免双重信号导致闪退
