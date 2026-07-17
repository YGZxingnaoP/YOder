import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QFileDialog, QLineEdit
)
from PySide6.QtCore import QUrl, QObject, Slot, Signal, Qt, QThread, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from func.chatbot.port import ChatClient
from func.chatbot.message_build import (
    build_message_list,
    create_record_folder,
    save_conversation,
    parse_error,
    list_conversations,
    rename_conversation,
    load_conversation,
    delete_conversation
)
from func.chatbot.memory_manager import load_memory
from func.files_reader.locate import get_file_tree
from func.files_reader.token_cal import calc_token_info
from func.ui.config import ConfigDialog

CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")

class WallpaperDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("壁纸设置")
        self.resize(400, 250)
        self.current_config = current_config or {}
        wp = self.current_config.get("wallpaper", {})
        self.image_path = wp.get("path", "")
        self.opacity = wp.get("opacity", 0.2)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self.image_path)
        path_layout.addWidget(QLabel("图片:"))
        path_layout.addWidget(self.path_edit)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_image)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("透明度:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.opacity * 100))
        self.opacity_label = QLabel(f"{self.opacity:.2f}")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v/100:.2f}"))
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        layout.addLayout(opacity_layout)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._on_accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择壁纸图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.path_edit.setText(path)

    def _on_accept(self):
        self.image_path = self.path_edit.text()
        self.opacity = self.opacity_slider.value() / 100
        self.accept()

    def get_values(self):
        return {"path": self.image_path, "opacity": self.opacity}

class StreamWorker(QObject):
    output = Signal(str, str)
    finished = Signal()

    def __init__(self, client, messages):
        super().__init__()
        self.client = client
        self.messages = messages

    @Slot()
    def run(self):
        def callback(type_, content):
            self.output.emit(type_, content)
        try:
            self.client.chat(self.messages, callback, stream=True)
        except Exception as e:
            self.output.emit("error", str(e))
        finally:
            self.finished.emit()

class Bridge(QObject):
    def __init__(self, web_view, main_window, parent=None):
        super().__init__(parent)
        self.web_view = web_view
        self.main_window = main_window
        self.client = ChatClient(CONFIG_PATH)
        self.current_folder = None
        self.current_messages = []
        self.current_root_path = ""
        self._assistant_text = ""
        self._thinking_text = ""
        self.worker = None
        self.worker_thread = None
        self._stream_active = False
        self._pending_stream = {"thinking": "", "content": ""}
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush_pending)

    def _run_js(self, code):
        self.web_view.page().runJavaScript(code)

    @Slot(str)
    def switch_conversation(self, folder_name):
        if self._stream_active:
            self._run_js("alert('请等待当前回复完成后再切换对话')")
            return
        self.current_folder = folder_name
        self.current_messages = load_conversation(folder_name) if folder_name else []
        if self.current_messages:
            self._run_js(f"loadHistory({json.dumps(self.current_messages)})")
        else:
            self._run_js("clearMessages()")
        # 确保切换对话后发送按钮可用
        self._run_js("if(typeof enableSendButton==='function')enableSendButton();")
        self.client.reload_config()

    @Slot(str, str)
    def rename_folder(self, old_name, new_name):
        if rename_conversation(old_name, new_name):
            self.load_conversation_list()
            if self.current_folder == old_name:
                self.current_folder = new_name
        else:
            self._run_js("alert('重命名失败')")

    @Slot(str)
    def delete_folder(self, folder_name):
        if delete_conversation(folder_name):
            if self.current_folder == folder_name:
                self.current_folder = None
                self.current_messages = []
                self._run_js("clearMessages()")
            self.load_conversation_list()
        else:
            self._run_js("alert('删除失败')")

    @Slot()
    def load_conversation_list(self):
        convs = list_conversations()
        self._run_js(f"updateConversationList({json.dumps(convs)})")

    @Slot(str)
    def load_folder(self, path):
        if not os.path.isdir(path):
            self._run_js("alert('文件夹不存在')")
            return
        self.current_root_path = path
        try:
            tree = get_file_tree(path)
            def enrich(node):
                if node["type"] == "file":
                    t, c = calc_token_info(node["path"])
                    node["token_count"] = t
                    node["char_count"] = c
                else:
                    for child in node.get("children", []):
                        enrich(child)
            enrich(tree)
            self._run_js(f"displayFileTree({json.dumps(tree)})")
        except Exception as e:
            self._run_js(f"alert('读取文件夹失败: {str(e)}')")

    def _do_send(self, text, files):
        if not self.current_folder:
            self.current_folder = create_record_folder()
            self.current_messages = []
            self.load_conversation_list()
        mem_rounds = self.client.config.get("memory_rounds", 50)
        history = load_memory(self.current_folder, mem_rounds)
        system_prompt = "You are a helpful assistant."
        messages, ui_content = build_message_list(
            system_prompt, text, history, files, self.current_root_path
        )
        user_msg_record = {
            "role": "user",
            "raw_text": text,
            "files": files,
            "content": ui_content
        }
        self.current_messages.append(user_msg_record)
        self._assistant_text = ""
        self._thinking_text = ""
        self._stream_active = True
        self.worker = StreamWorker(self.client, messages)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.output.connect(self._on_stream)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.finished.connect(self._on_stream_finished)
        self.worker_thread.start()

    @Slot(str, str)
    def send_message(self, text, files_json):
        if self._stream_active:
            self._run_js("alert('正在生成回答，请稍后')")
            return
        try:
            files = json.loads(files_json) if files_json else []
        except:
            files = []
        self._do_send(text, files)

    @Slot(str, str)
    def regenerate_message(self, text, files_json):
        if self._stream_active:
            return
        try:
            files = json.loads(files_json) if files_json else []
        except:
            files = []
        if self.current_messages and self.current_messages[-1]['role'] == 'assistant':
            self.current_messages.pop()
        if self.current_messages and self.current_messages[-1]['role'] == 'user':
            self.current_messages.pop()
        self._do_send(text, files)

    def _on_stream(self, type_, content):
        if type_ == "thinking":
            self._thinking_text += content
            self._pending_stream["thinking"] += content
        elif type_ == "content":
            self._assistant_text += content
            self._pending_stream["content"] += content
        elif type_ == "error":
            err = parse_error(content)
            self._run_js(f"addError({json.dumps(err)})")
            self._assistant_text = ""
            self._stream_active = False
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_pending(self):
        t = self._pending_stream["thinking"]
        c = self._pending_stream["content"]
        self._pending_stream["thinking"] = ""
        self._pending_stream["content"] = ""
        if t:
            self._run_js(f"addThinking({json.dumps(t)})")
        if c:
            self._run_js(f"addContent({json.dumps(c)})")

    def _on_stream_finished(self):
        self._flush_timer.stop()
        self._flush_pending()
        if self._assistant_text:
            self.current_messages.append({
                "role": "assistant",
                "thinking": self._thinking_text,
                "content": self._assistant_text
            })
            save_conversation(self.current_folder, self.current_messages)
            model = self.client.model
            self._run_js(f"finishMessage({json.dumps(model)})")
        else:
            self._run_js("finishMessage('')")
        self._assistant_text = ""
        self._thinking_text = ""
        self.worker = None
        self.worker_thread = None
        self._stream_active = False

    @Slot(str)
    def copy_to_clipboard(self, text):
        """通过 Qt 剪贴板复制文本，绕过浏览器剪贴板 API 限制"""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    @Slot()
    def open_settings(self):
        dialog = ConfigDialog(self.main_window)
        if dialog.exec():
            self.client.reload_config()
            self._run_js("alert('设置已保存')")

    @Slot()
    def open_wallpaper_settings(self):
        config = self.client.config
        dialog = WallpaperDialog(self.main_window, config)
        if dialog.exec():
            vals = dialog.get_values()
            config["wallpaper"] = vals
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            img_path = vals["path"]
            url = QUrl.fromLocalFile(img_path).toString() if img_path else ""
            self._run_js(f"setWallpaper('{url}', {vals['opacity']})")
            self._run_js("onWallpaperSettingsClosed()")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 代码辅助")
        self.resize(1200, 800)
        self.web_view = QWebEngineView()
        self.setCentralWidget(self.web_view)
        self.channel = QWebChannel()
        self.bridge = Bridge(self.web_view, self)
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template", "home.html")
        self.web_view.load(QUrl.fromLocalFile(html_path))
        self.web_view.loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok):
        if ok:
            QTimer.singleShot(1000, self._on_page_ready)

    def _on_page_ready(self):
        self.bridge.load_conversation_list()
        config = self.bridge.client.config
        wp = config.get("wallpaper", {})
        if wp.get("path"):
            url = QUrl.fromLocalFile(wp["path"]).toString()
            opacity = wp.get("opacity", 0.2)
            self.bridge._run_js(f"setWallpaper('{url}', {opacity})")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())