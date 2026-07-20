import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QFileDialog, QLineEdit, QCheckBox
)
from PySide6.QtCore import QUrl, QObject, Slot, Signal, Qt, QThread, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from func.chatbot.port import ChatClient, summarize_chat
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
from func.chatbot.memory_manager import (
    load_memory,
    load_memory_config,
    save_memory_config,
    load_model_config,
    save_model_config,
    load_wallpaper_config,
    save_wallpaper_config,
    should_trigger_summarize,
    build_summarize_messages,
    save_summary,
)
from func.files_reader.locate import get_file_tree
from func.files_reader.token_cal import calc_token_info
from func.ui.config import ConfigDialog, MemoryConfigDialog, ModelConfigDialog

CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")


class WallpaperDialog(QDialog):
    def __init__(self, parent=None, current_config=None, is_conversation_bound=False):
        super().__init__(parent)
        self.setWindowTitle("壁纸设置")
        self.resize(400, 280)
        self.current_config = current_config or {}
        wp = self.current_config.get("wallpaper", {})
        self.image_path = wp.get("path", "")
        self.opacity = wp.get("opacity", 0.2)
        self.is_bound = is_conversation_bound
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
        # 仅适用于该对话
        self.bind_check = QCheckBox("仅适用于当前对话")
        self.bind_check.setChecked(self.is_bound)
        layout.addWidget(self.bind_check)
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
        self.is_bound = self.bind_check.isChecked()
        self.accept()

    def get_values(self):
        return {"path": self.image_path, "opacity": self.opacity}

    def is_conversation_bound(self):
        return self.is_bound


class StreamWorker(QObject):
    output = Signal(str, str)
    finished = Signal()

    def __init__(self, client, messages, platform=None, model=None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.platform = platform
        self.model = model

    @Slot()
    def run(self):
        def callback(type_, content):
            self.output.emit(type_, content)
        try:
            if self.platform and self.model:
                self.client.chat_with_model(
                    self.messages, callback,
                    platform=self.platform, model=self.model
                )
            else:
                self.client.chat(self.messages, callback, stream=True)
        except Exception as e:
            self.output.emit("error", str(e))
        finally:
            self.finished.emit()


class SummarizeWorker(QObject):
    """后台概括工作线程"""
    done = Signal(str)
    error = Signal(str)

    def __init__(self, messages, config):
        super().__init__()
        self.messages = messages
        self.config = config

    @Slot()
    def run(self):
        try:
            text = summarize_chat(self.messages, self.config)
            self.done.emit(text)
        except Exception as e:
            self.error.emit(str(e))


class Bridge(QObject):
    def __init__(self, web_view, main_window, parent=None):
        super().__init__(parent)
        self.web_view = web_view
        self.main_window = main_window
        self.client = ChatClient(CONFIG_PATH)
        self.current_folder = None
        self.current_messages = []
        self.loaded_paths = {}
        self.current_path = ""
        self._assistant_text = ""
        self._thinking_text = ""
        self.worker = None
        self.worker_thread = None
        self._stream_active = False
        self._pending_stream = {"thinking": "", "content": ""}
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush_pending)
        # 对话级模型绑定
        self._conv_model = None   # {"platform":..., "model":...} or None
        # 后台概括状态
        self._summarizing = False
        # token 超限重试标记
        self._token_overflow_retry = False

    def _run_js(self, code):
        self.web_view.page().runJavaScript(code)

    def _get_effective_platform(self):
        if self._conv_model and self._conv_model.get("enabled", True) and self._conv_model.get("platform"):
            return self._conv_model["platform"]
        return self.client.platform

    def _get_effective_model(self):
        if self._conv_model and self._conv_model.get("enabled", True) and self._conv_model.get("model"):
            return self._conv_model["model"]
        return self.client.model

    @Slot(str)
    def switch_conversation(self, folder_name):
        if self._stream_active:
            self._run_js("alert('请等待当前回复完成后再切换对话')")
            return
        self.current_folder = folder_name
        try:
            self.current_messages = load_conversation(folder_name) if folder_name else []
        except Exception:
            self.current_messages = []
        if self.current_messages:
            self._run_js(f"loadHistory({json.dumps(self.current_messages)})")
        else:
            self._run_js("clearMessages()")
        self._run_js("if(typeof enableSendButton==='function')enableSendButton();")
        self.client.reload_config()
        # 加载对话级配置
        self._load_conv_configs(folder_name)

    def _load_conv_configs(self, folder_name):
        """加载对话级模型/壁纸配置并更新前端"""
        if not folder_name:
            self._conv_model = None
            self._run_js("showModelTag('')")
            return
        # 模型
        model_cfg = load_model_config(folder_name)
        self._conv_model = model_cfg
        # 只有 enabled=True 时才显示绑定标签
        if model_cfg and model_cfg.get("enabled", True):
            self._run_js(f"showModelTag({json.dumps(model_cfg.get('model', ''))})")
        else:
            # 未绑定或被禁用 → 显示全局模型
            self._run_js(f"showModelTag({json.dumps(self.client.model)})")
        # 壁纸
        wp_cfg = load_wallpaper_config(folder_name)
        if wp_cfg and wp_cfg.get("path"):
            url = QUrl.fromLocalFile(wp_cfg["path"]).toString()
            opacity = wp_cfg.get("opacity", 0.2)
            self._run_js(f"setWallpaper('{url}', {opacity})")
        else:
            # 回退到全局壁纸
            global_wp = self.client.config.get("wallpaper", {})
            if global_wp.get("path"):
                url = QUrl.fromLocalFile(global_wp["path"]).toString()
                opacity = global_wp.get("opacity", 0.2)
                self._run_js(f"setWallpaper('{url}', {opacity})")
            else:
                self._run_js("setWallpaper('', 0)")

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
            self.loaded_paths[path] = tree
            self.current_path = path
            paths_list = list(self.loaded_paths.keys())
            self._run_js(f"displayFileTree({json.dumps(tree)})")
            self._run_js(f"updatePathList({json.dumps(paths_list)}, {json.dumps(path)})")
        except Exception as e:
            self._run_js(f"alert('读取文件夹失败: {str(e)}')")

    @Slot(str)
    def switch_path(self, path):
        if path in self.loaded_paths:
            self.current_path = path
            tree = self.loaded_paths[path]
            self._run_js(f"displayFileTree({json.dumps(tree)})")

    @Slot()
    def refresh_current_path(self):
        if not self.current_path or not os.path.isdir(self.current_path):
            return
        try:
            tree = get_file_tree(self.current_path)
            def enrich(node):
                if node["type"] == "file":
                    t, c = calc_token_info(node["path"])
                    node["token_count"] = t
                    node["char_count"] = c
                else:
                    for child in node.get("children", []):
                        enrich(child)
            enrich(tree)
            self.loaded_paths[self.current_path] = tree
            self._run_js(f"displayFileTree({json.dumps(tree)})")
        except Exception as e:
            self._run_js(f"alert('刷新失败: {str(e)}')")

    @Slot(str)
    def remove_path(self, path):
        if path in self.loaded_paths:
            del self.loaded_paths[path]
            paths_list = list(self.loaded_paths.keys())
            if self.current_path == path:
                if paths_list:
                    self.current_path = paths_list[-1]
                    self._run_js(f"displayFileTree({json.dumps(self.loaded_paths[self.current_path])})")
                else:
                    self.current_path = ""
                    self._run_js("clearFileTree()")
            self._run_js(f"updatePathList({json.dumps(paths_list)}, {json.dumps(self.current_path)})")

    def _do_send(self, text, files, force_use_summary=False):
        if not self.current_folder:
            self.current_folder = create_record_folder()
            self.current_messages = []
            self.load_conversation_list()

        mem_rounds = self.client.config.get("memory_rounds", 50)
        history = load_memory(self.current_folder, mem_rounds,
                              force_use_summary=force_use_summary)

        system_prompt = "You are a helpful assistant."
        messages, ui_content = build_message_list(
            system_prompt, text, history, files, self.current_path
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
        self._token_overflow_retry = force_use_summary

        platform = self._get_effective_platform()
        model = self._get_effective_model()

        self.worker = StreamWorker(self.client, messages, platform, model)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.output.connect(self._on_stream)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker.finished.connect(self._on_stream_finished)
        self.worker_thread.start()

        if files:
            file_contents = {}
            for fpath in files:
                if os.path.isfile(fpath):
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                            file_contents[fpath] = f.read()
                    except Exception:
                        pass
            if file_contents:
                self._run_js(f"fillFileContents({json.dumps(json.dumps(file_contents, ensure_ascii=False))})")

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
        if self.current_folder:
            save_conversation(self.current_folder, self.current_messages)
        self._do_send(text, files)

    @Slot(str)
    def delete_turn(self, index_str):
        if self._stream_active:
            return
        try:
            index = int(index_str)
        except (ValueError, TypeError):
            return
        if index < 0 or index >= len(self.current_messages):
            return
        if self.current_messages[index]['role'] != 'user':
            return
        self.current_messages.pop(index)
        if index < len(self.current_messages) and self.current_messages[index]['role'] == 'assistant':
            self.current_messages.pop(index)
        if self.current_folder:
            save_conversation(self.current_folder, self.current_messages)
        self._run_js(f"loadHistory({json.dumps(self.current_messages)})")

    def _on_stream(self, type_, content):
        if type_ == "thinking":
            self._thinking_text += content
            self._pending_stream["thinking"] += content
        elif type_ == "content":
            self._assistant_text += content
            self._pending_stream["content"] += content
        elif type_ == "error":
            # 检测 token 超限错误
            is_token_overflow = any(kw in content.lower() for kw in [
                "token", "context_length", "too long", "maximum",
                "max_tokens", "limit exceeded", "超出", "过长"
            ])
            if is_token_overflow and not self._token_overflow_retry and self.current_folder:
                mem_cfg = load_memory_config(self.current_folder)
                if mem_cfg.get("enabled") and mem_cfg.get("summaries"):
                    # 有可用概括 → 自动用概括重试
                    self._stream_active = False
                    self._flush_timer.stop()
                    self._pending_stream = {"thinking": "", "content": ""}
                    # 移除刚添加的 user 消息
                    if self.current_messages and self.current_messages[-1]["role"] == "user":
                        user_msg = self.current_messages.pop()
                        text = user_msg.get("raw_text", "")
                        files = user_msg.get("files", [])
                        self._do_send(text, files, force_use_summary=True)
                        return
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
            model = self._get_effective_model()
            self._run_js(f"finishMessage({json.dumps(model)})")
        else:
            self._run_js("finishMessage('')")
        self._assistant_text = ""
        self._thinking_text = ""
        self.worker = None
        self.worker_thread = None
        self._stream_active = False
        self._token_overflow_retry = False
        # 触发后台概括
        self._maybe_trigger_summarize()

    def _maybe_trigger_summarize(self):
        """AI 回复结束后检查是否需要后台概括"""
        if not self.current_folder or self._summarizing:
            return
        if not should_trigger_summarize(self.current_folder):
            return

        summarize_msgs = build_summarize_messages(self.current_folder)
        if not summarize_msgs:
            return

        self._summarizing = True
        self._run_js("showSummarizeStatus('正在概括记忆...')")

        config = dict(self.client.config)
        # 使用对话绑定的模型
        if self._conv_model:
            config["platform"] = self._conv_model.get("platform", config.get("platform"))
            config["model"] = self._conv_model.get("model", config.get("model"))

        self._sum_worker = SummarizeWorker(summarize_msgs, config)
        self._sum_thread = QThread()
        self._sum_worker.moveToThread(self._sum_thread)
        self._sum_thread.started.connect(self._sum_worker.run)
        self._sum_worker.done.connect(self._on_summarize_done)
        self._sum_worker.error.connect(self._on_summarize_error)
        self._sum_worker.done.connect(self._sum_thread.quit)
        self._sum_worker.error.connect(self._sum_thread.quit)
        self._sum_worker.done.connect(self._sum_worker.deleteLater)
        self._sum_worker.error.connect(self._sum_worker.deleteLater)
        self._sum_thread.finished.connect(self._sum_thread.deleteLater)
        self._sum_thread.start()

    def _on_summarize_done(self, summary_text):
        """概括完成, 3秒后标记就绪"""
        if self.current_folder and summary_text:
            save_summary(self.current_folder, summary_text)
        QTimer.singleShot(3000, self._mark_summarize_complete)

    def _on_summarize_error(self, error_msg):
        self._summarizing = False
        self._run_js(f"showSummarizeStatus('概括失败: {error_msg}')")
        # 5秒后清除状态
        QTimer.singleShot(5000, lambda: self._run_js("showSummarizeStatus('')"))

    def _mark_summarize_complete(self):
        self._summarizing = False
        self._run_js("showSummarizeStatus('记忆概括完成 ✓')")
        QTimer.singleShot(3000, lambda: self._run_js("showSummarizeStatus('')"))

    @Slot(str)
    def copy_to_clipboard(self, text):
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
    def open_memory_settings(self):
        """打开记忆概括配置对话框"""
        if not self.current_folder:
            self._run_js("alert('请先创建或选择一个对话')")
            return
        mem_cfg = load_memory_config(self.current_folder)
        dialog = MemoryConfigDialog(self.main_window, mem_cfg)
        if dialog.exec():
            save_memory_config(self.current_folder, dialog.get_config())
            self._run_js("alert('记忆设置已保存')")

    @Slot()
    def open_model_dialog(self):
        """打开对话级模型选择对话框"""
        if not self.current_folder:
            self._run_js("alert('请先创建或选择一个对话')")
            return
        platform = self._get_effective_platform()
        model = self._get_effective_model()
        # 判断当前是否已有且启用了绑定
        is_enabled = bool(self._conv_model and self._conv_model.get("enabled", True))
        dialog = ModelConfigDialog(self.main_window, platform, model, is_enabled)
        if dialog.exec():
            if dialog.is_cleared():
                # 清除绑定：删除 model.json，回退到全局配置
                model_json = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "records", self.current_folder, "model.json"
                )
                if os.path.exists(model_json):
                    os.remove(model_json)
                self._conv_model = None
                self.client.reload_config()
                self._run_js(f"showModelTag({json.dumps(self.client.model)})")
            else:
                new_platform, new_model = dialog.get_values()
                enabled = dialog.is_enabled()
                cfg = {"platform": new_platform, "model": new_model, "enabled": enabled}
                save_model_config(self.current_folder, cfg)
                self._conv_model = cfg
                if enabled:
                    self._run_js(f"showModelTag({json.dumps(new_model)})")
                else:
                    self.client.reload_config()
                    self._run_js(f"showModelTag({json.dumps(self.client.model)})")

    @Slot(str, str)
    def set_conversation_model(self, platform, model):
        """设置当前对话绑定的模型"""
        if not self.current_folder:
            self._run_js("alert('请先创建或选择一个对话')")
            return
        cfg = {"platform": platform, "model": model}
        save_model_config(self.current_folder, cfg)
        self._conv_model = cfg
        self._run_js(f"showModelTag({json.dumps(model)})")

    @Slot(str, str)
    def update_model_binding(self, platform, model):
        """前端调用: 更新模型绑定"""
        if not self.current_folder:
            return
        if platform and model:
            cfg = {"platform": platform, "model": model}
            save_model_config(self.current_folder, cfg)
            self._conv_model = cfg
        else:
            # 清除绑定
            self._conv_model = None

    @Slot(result=str)
    def get_current_model_info(self):
        """返回当前对话的模型信息 JSON"""
        platform = self._get_effective_platform()
        model = self._get_effective_model()
        is_bound = self._conv_model is not None
        return json.dumps({
            "platform": platform,
            "model": model,
            "is_bound": is_bound
        })

    @Slot(result=str)
    def get_summary_content(self):
        """返回当前对话的概括内容，用于侧边栏展示"""
        if not self.current_folder:
            return ""
        mem_cfg = load_memory_config(self.current_folder)
        summaries = mem_cfg.get("summaries", [])
        if not summaries:
            return "暂无概括内容"
        parts = []
        for i, s in enumerate(summaries, 1):
            rs = s.get("round_start", 0)
            re = s.get("round_end", 0)
            parts.append(f"═══ 概括段 {i}（第 {rs+1}-{re} 轮）═══\n{s['content']}")
        return "\n\n".join(parts)

    @Slot()
    def open_wallpaper_settings(self):
        if not self.current_folder:
            # 无对话时只能设全局
            is_bound = False
        else:
            is_bound = load_wallpaper_config(self.current_folder) is not None
        config = self.client.config
        dialog = WallpaperDialog(self.main_window, config, is_bound)
        if dialog.exec():
            vals = dialog.get_values()
            if dialog.is_conversation_bound() and self.current_folder:
                # 保存到对话文件夹
                save_wallpaper_config(self.current_folder, vals)
            else:
                # 保存到全局配置
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
        self.setWindowTitle("YODER")
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
