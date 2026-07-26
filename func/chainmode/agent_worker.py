"""
agent_worker.py - Agent 模式的 QThread 工作线程
四阶段管线，支持 stop 信号和命名思考块。
"""
import json
from PySide6.QtCore import QObject, Slot, Signal

from .agent_core import run_agent_pipeline


class AgentWorker(QObject):
    """
    在后台线程中运行 Agent 四阶段管线。

    信号:
    - progress(status: str, tasklist_json: str)  更新 tasklist 进度
    - stream(type: str, content: str)            流式输出
        type = "content"    → 最终输出内容
        type = "fold:名称"  → 命名折叠块内容
    - stopped(question: str)                     AI 叫停，向用户提问
    - finished()                                 完成
    - error(msg: str)                            出错
    """
    progress = Signal(str, str)
    stream = Signal(str, str)
    stopped = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, client, model, platform, user_message,
                 selected_files, root_path="", thinking_level="high",
                 history=None, max_tokens=65536, temperature=0.7,
                 system_prompt="", conversation_folder="", agent_mode=""):
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
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.conversation_folder = conversation_folder
        self.agent_mode = agent_mode
        self._user_stopped = False  # 用户主动停止标志

    def request_stop(self):
        """UI 调用：请求停止输出（已生成内容保留）"""
        self._user_stopped = True

    def is_stopped(self):
        """stop_check 回调：返回用户是否请求了停止"""
        return self._user_stopped

    @Slot()
    def run(self):
        try:
            def progress_cb(status, tasklist):
                self.progress.emit(status, json.dumps(tasklist, ensure_ascii=False))

            def stream_cb(type_, content):
                self.stream.emit(type_, content)

            def stop_cb(question):
                self.stopped.emit(question)

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
                thinking_callback=None,  # 思考通过 fold 块在 stream_callback 中处理
                history=self.history,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system_prompt=self.system_prompt,
                conversation_folder=self.conversation_folder,
                stop_callback=stop_cb,
                agent_mode=self.agent_mode,
                user_stop_check=self.is_stopped,
            )
            self.finished.emit()
        except Exception as e:
            # 用户停止时可能抛出异常，静默忽略
            if not self._user_stopped:
                self.error.emit(str(e))
            else:
                self.finished.emit()
