import sys
import os
import json
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QFileDialog, QLineEdit, QCheckBox
)
from PySide6.QtCore import QUrl, QObject, Slot, Signal, Qt, QThread, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from func.chatbot.port import ChatClient, summarize_chat
from func.chatbot.message_build import (
    build_message_list, create_record_folder, save_conversation, parse_error,
    list_conversations, rename_conversation, load_conversation, delete_conversation
)
from func.chatbot.memory_manager import (
    load_memory, load_memory_config, save_memory_config, load_model_config,
    save_model_config, load_wallpaper_config, save_wallpaper_config,
    load_agent_config, save_agent_config,
    should_trigger_summarize, build_summarize_messages, save_summary,
)
from func.files_reader.locate import get_file_tree
from func.files_reader.token_cal import calc_token_info
from func.ui.config import ConfigDialog, MemoryConfigDialog, ModelConfigDialog
from func.chainmode.agent_worker import AgentWorker

CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")


class WallpaperDialog(QDialog):
    # ... 保持原样，此处省略以节省篇幅，实际使用时请保留完整类定义 ...
    pass


class StreamWorker(QObject):
    output = Signal(str, str)
    finished = Signal()
    def __init__(self, client, messages, platform=None, model=None):
        super().__init__()
        self.client, self.messages, self.platform, self.model = client, messages, platform, model

    @Slot()
    def run(self):
        def callback(type_, content):
            self.output.emit(type_, content)
        try:
            if self.platform and self.model:
                self.client.chat_with_model(self.messages, callback, platform=self.platform, model=self.model)
            else:
                self.client.chat(self.messages, callback, stream=True)
        except Exception as e:
            self.output.emit("error", str(e))
        finally:
            self.finished.emit()


class SummarizeWorker(QObject):
    done = Signal(str)
    error = Signal(str)
    def __init__(self, messages, config, folder_name):
        super().__init__()
        self.messages, self.config, self.folder_name = messages, config, folder_name

    @Slot()
    def run(self):
        try:
            self.done.emit(summarize_chat(self.messages, self.config))
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
        self._pending_block_events = []  # [("thinking"|"content", text), ...]
        self._current_block_type = None  # "thinking" | "content" | None
        self._blocks = []  # [{"type": "thinking"|"content", "text": "..."}, ...]
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._conv_model = None
        self._chain_mode = False  # Agent 模式状态
        self._summarizing = False
        self._token_overflow_retry = False
        self.generating_folder = None
        self.active_gen_messages = None
        self.last_save_time = 0

    def _run_js(self, code):
        try:
            self.web_view.page().runJavaScript(code)
        except Exception as e:
            print(f"JS执行错误: {e}")

    def _get_filelist_path(self, folder_name):
        return os.path.join(BASE_DIR, "records", folder_name, "filelist.json")

    def _load_filelist(self, folder_name):
        path = self._get_filelist_path(folder_name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"paths": [], "selected": []}

    def _save_filelist(self, folder_name, data):
        if not folder_name:
            return
        path = self._get_filelist_path(folder_name)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存文件列表失败: {e}")

    def _get_effective_platform(self):
        if self._conv_model and self._conv_model.get("enabled", True) and self._conv_model.get("platform"):
            return self._conv_model["platform"]
        return self.client.platform

    def _get_effective_model(self):
        if self._conv_model and self._conv_model.get("enabled", True) and self._conv_model.get("model"):
            return self._conv_model["model"]
        return self.client.model

    def _update_summary_cache(self):
        if not self.current_folder:
            self._run_js("updateSummaryContent('')")
            return
        content = self.get_summary_content()
        self._run_js(f"updateSummaryContent({json.dumps(content)})")

    @Slot(str)
    def switch_conversation(self, folder_name):
        self.current_folder = folder_name
        try:
            self.current_messages = load_conversation(folder_name) if folder_name else []
        except:
            self.current_messages = []
            
        if self.current_messages:
            self._run_js(f"loadHistory({json.dumps(self.current_messages)})")
        else:
            self._run_js("clearMessages()")
        self._run_js("if(typeof enableSendButton==='function')enableSendButton();")
        # 延迟安全调用，确保前端异步操作完成后按钮仍然可用
        QTimer.singleShot(500, lambda: self._run_js(
            "if(typeof enableSendButton==='function')enableSendButton();"
        ))
        self.client.reload_config()
        self._load_conv_configs(folder_name)
        
        if folder_name:
            fl = self._load_filelist(folder_name)
            self._run_js(f"loadSavedPaths({json.dumps(fl.get('paths', []))}, {json.dumps(fl.get('selected', []))})")
        else:
            self._run_js("clearFileTree()")
        
        self._update_summary_cache()

    def _load_conv_configs(self, folder_name):
        if not folder_name:
            self._conv_model = None
            self._chain_mode = False
            self._run_js("showModelTag('')")
            self._run_js("toggleSummaryBtn(false)")
            self._run_js("setChainMode(false)")
            return
            
        mem_cfg = load_memory_config(folder_name)
        is_mem_enabled = mem_cfg.get("enabled", False) if mem_cfg else False
        self._run_js(f"toggleSummaryBtn({'true' if is_mem_enabled else 'false'})")

        model_cfg = load_model_config(folder_name)
        self._conv_model = model_cfg
        if model_cfg and model_cfg.get("enabled", True):
            self._run_js(f"showModelTag({json.dumps(model_cfg.get('model', ''))})")
        else:
            self._run_js(f"showModelTag({json.dumps(self.client.model)})")

        # 恢复 Agent 模式配置
        agent_cfg = load_agent_config(folder_name)
        self._chain_mode = agent_cfg.get("chain_mode", False)
        self._run_js(f"setChainMode({'true' if self._chain_mode else 'false'})")
            
        wp_cfg = load_wallpaper_config(folder_name)
        if wp_cfg and wp_cfg.get("path"):
            self._run_js(f"setWallpaper('{QUrl.fromLocalFile(wp_cfg['path']).toString()}', {wp_cfg.get('opacity', 0.2)})")
        else:
            global_wp = self.client.config.get("wallpaper", {})
            if global_wp.get("path"):
                self._run_js(f"setWallpaper('{QUrl.fromLocalFile(global_wp['path']).toString()}', {global_wp.get('opacity', 0.2)})")
            else:
                self._run_js("setWallpaper('', 0)")

    @Slot(str)
    def save_file_selection(self, files_json):
        if not self.current_folder:
            return
        try:
            files = json.loads(files_json)
        except:
            files = []
        fl = self._load_filelist(self.current_folder)
        fl["selected"] = files
        self._save_filelist(self.current_folder, fl)

    @Slot(str)
    def load_cached_folders(self, paths_json):
        try:
            paths = json.loads(paths_json)
        except:
            return
        # 只加载存在的路径，并更新缓存
        for p in paths:
            if os.path.isdir(p):
                try:
                    tree = get_file_tree(p)
                    def enrich(node):
                        if node["type"] == "file":
                            t, c = calc_token_info(node["path"])
                            node["token_count"], node["char_count"] = t, c
                        else:
                            for child in node.get("children", []):
                                enrich(child)
                    enrich(tree)
                    self.loaded_paths[p] = tree
                    self.current_path = p
                    # 直接显示这个树
                    self._run_js(f"displayFileTree({json.dumps(tree)})")
                except Exception as e:
                    print(f"加载路径 {p} 失败: {e}")
        # 更新路径下拉列表
        self._run_js(f"updatePathList({json.dumps(list(self.loaded_paths.keys()))}, {json.dumps(self.current_path)})")

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
                self._run_js("clearFileTree()")
            self.load_conversation_list()
        else:
            self._run_js("alert('删除失败')")

    @Slot()
    def load_conversation_list(self):
        self._run_js(f"updateConversationList({json.dumps(list_conversations())})")

    @Slot(str)
    def load_folder(self, path):
        if not os.path.isdir(path):
            self._run_js("alert('文件夹不存在')")
            return
        try:
            tree = get_file_tree(path)
            if not tree:
                self._run_js("alert('读取文件夹返回空结构')")
                return
            def enrich(node):
                if node["type"] == "file":
                    t, c = calc_token_info(node["path"])
                    node["token_count"], node["char_count"] = t, c
                else:
                    for child in node.get("children", []):
                        enrich(child)
            enrich(tree)
            self.loaded_paths[path] = tree
            self.current_path = path
            try:
                tree_json = json.dumps(tree)
            except Exception as e:
                self._run_js(f"alert('文件树数据过大，无法序列化: {str(e)}')")
                return
            self._run_js(f"displayFileTree({tree_json})")
            self._run_js(f"updatePathList({json.dumps(list(self.loaded_paths.keys()))}, {json.dumps(path)})")
            
            # 修复：确保路径总是能被保存到 filelist
            # 如果 current_folder 为空，创建一个临时文件夹
            folder_to_save = self.current_folder
            if not folder_to_save:
                folder_to_save = create_record_folder()
                self.current_folder = folder_to_save
                self.current_messages = []
                self.load_conversation_list()
            
            fl = self._load_filelist(folder_to_save)
            if path not in fl["paths"]:
                fl["paths"].append(path)
                self._save_filelist(folder_to_save, fl)
        except Exception as e:
            self._run_js(f"alert('读取文件夹失败: {str(e)}')")

    @Slot(str)
    def switch_path(self, path):
        if path in self.loaded_paths:
            self.current_path = path
            self._run_js(f"displayFileTree({json.dumps(self.loaded_paths[path])})")

    @Slot()
    def refresh_current_path(self):
        if not self.current_path or not os.path.isdir(self.current_path):
            return
        try:
            tree = get_file_tree(self.current_path)
            def enrich(node):
                if node["type"] == "file":
                    node["token_count"], node["char_count"] = calc_token_info(node["path"])
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
                self.current_path = paths_list[-1] if paths_list else ""
                if self.current_path:
                    self._run_js(f"displayFileTree({json.dumps(self.loaded_paths[self.current_path])})")
                else:
                    self._run_js("clearFileTree()")
            self._run_js(f"updatePathList({json.dumps(paths_list)}, {json.dumps(self.current_path)})")
            
            if self.current_folder:
                fl = self._load_filelist(self.current_folder)
                if path in fl["paths"]:
                    fl["paths"].remove(path)
                self._save_filelist(self.current_folder, fl)

    # ========== 核心修复：增加异常捕获和用户反馈 ==========
    def _do_send(self, text, files, force_use_summary=False):
        self._flush_timer.stop()
        self._pending_block_events = []
        self._current_block_type = None
        self._blocks = []
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(1000)

        try:
            if not self.current_folder:
                self.current_folder = create_record_folder()
                self.current_messages = []
                self.load_conversation_list()

            mem_rounds = self.client.config.get("memory_rounds", 50)
            history = load_memory(self.current_folder, mem_rounds, force_use_summary=force_use_summary)
            messages, ui_content = build_message_list("You are a helpful assistant.", text, history, files, self.current_path)

            self.current_messages.append({"role": "user", "raw_text": text, "files": files, "content": ui_content, "chain_mode": False})
            self.current_messages.append({"role": "assistant", "thinking": "", "content": "", "blocks": []})
            save_conversation(self.current_folder, self.current_messages)

            self._assistant_text = ""
            self._thinking_text = ""
            self._pending_block_events = []
            self._current_block_type = None
            self._blocks = []
            self._stream_active = True
            self._token_overflow_retry = force_use_summary
            self.generating_folder = self.current_folder
            self.active_gen_messages = self.current_messages
            self.last_save_time = time.time()

            self.worker = StreamWorker(self.client, messages, self._get_effective_platform(), self._get_effective_model())
            self.worker_thread = QThread()
            self.worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.worker.run)
            self.worker.output.connect(self._on_stream)
            self.worker.finished.connect(self.worker_thread.quit)
            self.worker_thread.finished.connect(self._on_stream_finished)
            self.worker_thread.start()

            if files:
                file_contents = {}
                for fpath in files:
                    if os.path.isfile(fpath):
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                                content = f.read()
                                if len(content) > 10000:
                                    content = content[:10000] + "\n\n...[文件过大，仅展示前一万字]..."
                                file_contents[fpath] = content
                        except:
                            pass
                if file_contents:
                    self._run_js(f"fillFileContents({json.dumps(file_contents)})")
        except Exception as e:
            self._stream_active = False
            self.generating_folder = None
            self.active_gen_messages = None
            self._run_js(f"addError({json.dumps(f'发送失败: {str(e)}')})")
            self._run_js("enableSendButton()")

    @Slot(str, str)
    def send_message(self, text, files_json):
        if self._stream_active:
            self._run_js("addError('正在生成中，请稍候...')")
            return
        try:
            files = json.loads(files_json) if files_json else []
            self._do_send(text, files)
        except Exception as e:
            self._run_js(f"addError({json.dumps(f'发送失败: {str(e)}')})")
            self._run_js("enableSendButton()")

    @Slot(str, str, str)
    def send_message_with_config(self, text, files_json, config_json):
        """接收前端对话配置，支持思维链模式和独立模型配置"""
        if self._stream_active:
            self._run_js("addError('正在生成中，请稍候...')")
            return
        try:
            files = json.loads(files_json) if files_json else []
            cfg = json.loads(config_json) if config_json else {}
        except:
            files = []
            cfg = {}

        chain_mode = cfg.get("chainMode", False)

        # 一旦对话开启了 Agent 模式，始终使用
        if self._chain_mode:
            chain_mode = True

        # 保存 Agent 模式配置到对话文件夹
        if chain_mode:
            self._chain_mode = True
            if self.current_folder:
                save_agent_config(self.current_folder, {"chain_mode": True})

        # 应用独立模型配置
        if cfg.get("independentModel") and cfg.get("platform") and cfg.get("model"):
            self._conv_model = {
                "enabled": True,
                "platform": cfg["platform"],
                "model": cfg["model"]
            }
            # 同时保存对话级配置
            if self.current_folder:
                save_model_config(self.current_folder, self._conv_model)
            # 应用 max_tokens 和 memory_rounds
            if cfg.get("maxTokens"):
                self.client.max_tokens = cfg["maxTokens"]
            if cfg.get("memRounds"):
                self.client.config["memory_rounds"] = cfg["memRounds"]

        if chain_mode:
            self._do_agent_send(text, files)
        else:
            self._do_send(text, files)

    @Slot(str, str, str)
    def regenerate_message(self, text, files_json, config_json):
        if self._stream_active:
            self._run_js("addError('正在生成中，请稍候...')")
            return
        try:
            files = json.loads(files_json) if files_json else []
            cfg = json.loads(config_json) if config_json else {}
            chain_mode = cfg.get("chainMode", False)
            # 一旦对话开启了 Agent 模式，始终使用
            if self._chain_mode:
                chain_mode = True
            if self.current_messages and self.current_messages[-1]['role'] == 'assistant':
                self.current_messages.pop()
            if self.current_messages and self.current_messages[-1]['role'] == 'user':
                self.current_messages.pop()
            if self.current_folder:
                save_conversation(self.current_folder, self.current_messages)
            if chain_mode:
                self._do_agent_send(text, files)
            else:
                self._do_send(text, files)
        except Exception as e:
            self._run_js(f"addError({json.dumps(f'重新生成失败: {str(e)}')})")
            self._run_js("enableSendButton()")
    # ========== 修复结束 ==========

    def _do_agent_send(self, text, files):
        """思维链模式: 使用 Agent 流程执行"""
        from openai import OpenAI
        from func.chatbot.port import PLATFORM_BASE_URLS

        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(1000)

        try:
            if not self.current_folder:
                self.current_folder = create_record_folder()
                self.current_messages = []
                self.load_conversation_list()

            # 确保 Agent 模式配置已保存
            if self._chain_mode:
                save_agent_config(self.current_folder, {"chain_mode": True})

            # 保存用户消息
            self.current_messages.append({"role": "user", "raw_text": text, "files": files, "content": text, "chain_mode": True})
            self.current_messages.append({"role": "assistant", "thinking": "", "content": "", "blocks": []})
            save_conversation(self.current_folder, self.current_messages)

            self._assistant_text = ""
            self._thinking_text = ""
            self._pending_block_events = []
            self._current_block_type = None
            self._blocks = []
            self._stream_active = True
            self.generating_folder = self.current_folder
            self.active_gen_messages = self.current_messages
            self.last_save_time = time.time()

            # 确定平台和模型
            platform = self._get_effective_platform()
            model = self._get_effective_model()
            keys = self.client.config.get("api_keys", {})
            api_key = keys.get(platform, "")
            base_url = PLATFORM_BASE_URLS.get(platform, "")
            if not api_key or not base_url:
                raise ValueError(f"{platform} API Key 未配置")

            agent_client = OpenAI(api_key=api_key, base_url=base_url)

            # 加载对话历史（不含当前轮，当前轮刚已追加）
            mem_rounds = self.client.config.get("memory_rounds", 50)
            agent_history = load_memory(self.current_folder, mem_rounds)
            if len(agent_history) >= 2:
                agent_history = agent_history[:-2]  # 排除当前 user + assistant 占位

            # 创建 AgentWorker
            self.worker = AgentWorker(
                client=agent_client,
                model=model,
                platform=platform,
                user_message=text,
                selected_files=files,
                root_path=self.current_path,
                thinking_level=self.client.thinking_level,
                history=agent_history
            )
            self.worker_thread = QThread()
            self.worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.worker.run)

            # 连接信号
            self.worker.progress.connect(self._on_agent_progress)
            self.worker.stream.connect(self._on_agent_stream)
            self.worker.finished.connect(self._on_agent_finished)
            self.worker.error.connect(self._on_agent_error)

            self.worker.finished.connect(self.worker_thread.quit)
            self.worker.error.connect(self.worker_thread.quit)
            self.worker_thread.finished.connect(self._cleanup_agent_thread)

            self.worker_thread.start()

            # 填充文件内容到 UI
            if files:
                file_contents = {}
                for fpath in files:
                    if os.path.isfile(fpath):
                        try:
                            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                                content = f.read()
                                if len(content) > 10000:
                                    content = content[:10000] + "\n\n...[文件过大，仅展示前一万字]..."
                                file_contents[fpath] = content
                        except:
                            pass
                if file_contents:
                    self._run_js(f"fillFileContents({json.dumps(file_contents)})")
        except Exception as e:
            self._stream_active = False
            self.generating_folder = None
            self.active_gen_messages = None
            self._run_js(f"addError({json.dumps(f'思维链模式启动失败: {str(e)}')})")
            self._run_js("enableSendButton()")
            self._run_js("updateChainProgress('', '[]')")

    def _cleanup_agent_thread(self):
        """安全清理 Agent 工作线程（在主线程中执行）"""
        if self.worker:
            try:
                self.worker.progress.disconnect()
                self.worker.stream.disconnect()
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except:
                pass
        self.worker = None
        self.worker_thread = None

    def _on_agent_progress(self, status, tasklist_json):
        """Agent 进度更新"""
        self._run_js(f"updateChainProgress({json.dumps(status)}, {json.dumps(tasklist_json)})")

    def _on_agent_stream(self, type_, content):
        """Agent 流式输出 - 支持思考/内容交错"""
        if type_ == "thinking":
            self._thinking_text += content
        elif type_ == "content":
            self._assistant_text += content

        # 检测块类型切换
        if type_ in ("thinking", "content") and self._current_block_type != type_:
            self._current_block_type = type_
            self._blocks.append({"type": type_, "text": ""})
            self._pending_block_events.append((type_, ""))

        # 追加到当前块
        if self._blocks and type_ in ("thinking", "content"):
            self._blocks[-1]["text"] += content
            self._pending_block_events.append((type_, content))

        if self.active_gen_messages and self.active_gen_messages[-1]["role"] == "assistant":
            self.active_gen_messages[-1]["thinking"] = self._thinking_text
            self.active_gen_messages[-1]["content"] = self._assistant_text
            self.active_gen_messages[-1]["blocks"] = list(self._blocks)

        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _on_agent_finished(self):
        """Agent 完成"""
        self._flush_timer.stop()
        self._flush_pending()

        if self.generating_folder and self.active_gen_messages:
            if self.active_gen_messages[-1]["role"] == "assistant":
                self.active_gen_messages[-1]["thinking"] = self._thinking_text
                self.active_gen_messages[-1]["content"] = self._assistant_text
                self.active_gen_messages[-1]["blocks"] = list(self._blocks)
                self.active_gen_messages[-1]["model"] = self._get_effective_model()
            save_conversation(self.generating_folder, self.active_gen_messages)

        if self.generating_folder == self.current_folder:
            if self._assistant_text:
                self._run_js(f"finishMessage({json.dumps(self._get_effective_model())})")
            else:
                self._run_js("finishMessage('')")
        else:
            self._run_js("if(typeof enableSendButton==='function')enableSendButton();")

        self._run_js("updateChainProgress('', '[]')")
        self._assistant_text = self._thinking_text = ""
        self._pending_block_events = []
        self._current_block_type = None
        self._blocks = []
        self._stream_active = False
        gen_folder = self.generating_folder
        self.generating_folder = self.active_gen_messages = None
        self._maybe_trigger_summarize(gen_folder)

    def _on_agent_error(self, error_msg):
        """Agent 出错"""
        self._stream_active = False
        self._flush_timer.stop()
        self._run_js(f"addError({json.dumps(f'思维链模式错误: {error_msg}')})")
        self._run_js("enableSendButton()")
        self._run_js("updateChainProgress('', '[]')")
        self.generating_folder = None
        self.active_gen_messages = None
        # 线程清理由 _cleanup_agent_thread 信号槽处理

    @Slot(str)
    def delete_turn(self, index_str):
        if self._stream_active:
            return
        try:
            index = int(index_str)
        except:
            return
        if index < 0 or index >= len(self.current_messages) or self.current_messages[index]['role'] != 'user':
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
        elif type_ == "content":
            self._assistant_text += content

        # 检测块类型切换（普通对话也支持交错）
        if type_ in ("thinking", "content") and self._current_block_type != type_:
            self._current_block_type = type_
            self._blocks.append({"type": type_, "text": ""})
            self._pending_block_events.append((type_, ""))

        if self._blocks and type_ in ("thinking", "content"):
            self._blocks[-1]["text"] += content
            self._pending_block_events.append((type_, content))

        if type_ == "error":
            # token 溢出重试逻辑
            if any(kw in content.lower() for kw in ["token", "context_length", "too long", "maximum"]) and not self._token_overflow_retry and self.current_folder:
                mem_cfg = load_memory_config(self.current_folder)
                if mem_cfg.get("enabled") and mem_cfg.get("summaries"):
                    self._stream_active = False
                    self._flush_timer.stop()
                    if self.current_messages and self.current_messages[-1]["role"] == "assistant":
                        self.current_messages.pop()
                    if self.current_messages and self.current_messages[-1]["role"] == "user":
                        user_msg = self.current_messages.pop()
                        self._do_send(user_msg.get("raw_text", ""), user_msg.get("files", []), force_use_summary=True)
                        return
            # 记录错误到消息
            if self.active_gen_messages and self.active_gen_messages[-1]["role"] == "assistant":
                self.active_gen_messages[-1]["content"] = f"Error: {parse_error(content)}"
                if self.generating_folder:
                    save_conversation(self.generating_folder, self.active_gen_messages)
            self._run_js(f"addError({json.dumps(parse_error(content))})")
            self._stream_active = False
            self.generating_folder = None
            self._run_js("enableSendButton()")

        if self.active_gen_messages and self.active_gen_messages[-1]["role"] == "assistant":
            self.active_gen_messages[-1]["thinking"] = self._thinking_text
            self.active_gen_messages[-1]["content"] = self._assistant_text
            self.active_gen_messages[-1]["blocks"] = list(self._blocks)

        if self.generating_folder and self.active_gen_messages and time.time() - self.last_save_time > 2.0:
            save_conversation(self.generating_folder, self.active_gen_messages)
            self.last_save_time = time.time()

        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_pending(self):
        events = self._pending_block_events
        self._pending_block_events = []
        for type_, text in events:
            if text:
                self._run_js(f"addBlock({json.dumps(type_)}, {json.dumps(text)})")

    def _on_stream_finished(self):
        self._flush_timer.stop()
        self._flush_pending()
        if self.generating_folder and self.active_gen_messages:
            if self.active_gen_messages[-1]["role"] == "assistant":
                self.active_gen_messages[-1]["thinking"] = self._thinking_text
                self.active_gen_messages[-1]["content"] = self._assistant_text
                self.active_gen_messages[-1]["blocks"] = list(self._blocks)
                self.active_gen_messages[-1]["model"] = self._get_effective_model()
            save_conversation(self.generating_folder, self.active_gen_messages)

        if self.generating_folder == self.current_folder:
            if self._assistant_text:
                self._run_js(f"finishMessage({json.dumps(self._get_effective_model())})")
            else:
                self._run_js("finishMessage('')")
        else:
            self._run_js("if(typeof enableSendButton==='function')enableSendButton();")

        self._assistant_text = self._thinking_text = ""
        self._pending_block_events = []
        self._current_block_type = None
        self._blocks = []
        self._stream_active = self._token_overflow_retry = False
        gen_folder = self.generating_folder
        self.generating_folder = self.active_gen_messages = None
        # 安全清理 StreamWorker 线程
        if self.worker_thread and self.worker_thread.isFinished():
            self.worker = None
            self.worker_thread = None
        self._maybe_trigger_summarize(gen_folder)

    def _maybe_trigger_summarize(self, folder_name=None):
        target_folder = folder_name or self.current_folder
        if not target_folder or self._summarizing or not should_trigger_summarize(target_folder):
            return
        summarize_msgs = build_summarize_messages(target_folder)
        if not summarize_msgs:
            return

        self._summarizing = True
        if target_folder == self.current_folder:
            self._run_js("showSummarizeStatus('正在概括记忆...')")
        
        config = dict(self.client.config)
        model_cfg = load_model_config(target_folder)
        if model_cfg and model_cfg.get("enabled", True):
            config["platform"] = model_cfg.get("platform", config.get("platform"))
            config["model"] = model_cfg.get("model", config.get("model"))

        self._sum_worker = SummarizeWorker(summarize_msgs, config, target_folder)
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
        folder_name = self._sum_worker.folder_name
        if folder_name and summary_text:
            save_summary(folder_name, summary_text)
        if folder_name == self.current_folder:
            QTimer.singleShot(3000, self._mark_summarize_complete)
            self._update_summary_cache()
        else:
            self._summarizing = False

    def _on_summarize_error(self, error_msg):
        self._summarizing = False
        if self._sum_worker.folder_name == self.current_folder:
            self._run_js(f"showSummarizeStatus('概括失败: {error_msg}')")
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
        if ConfigDialog(self.main_window).exec():
            self.client.reload_config()
            self._run_js("alert('设置已保存')")

    @Slot()
    def open_memory_settings(self):
        if not self.current_folder:
            return self._run_js("alert('请先创建或选择一个对话')")
        dialog = MemoryConfigDialog(self.main_window, load_memory_config(self.current_folder))
        if dialog.exec():
            save_memory_config(self.current_folder, dialog.get_config())
            self._run_js("alert('记忆设置已保存')")
            mem_cfg = load_memory_config(self.current_folder)
            self._run_js(f"toggleSummaryBtn({'true' if mem_cfg.get('enabled') else 'false'})")
            self._update_summary_cache()

    @Slot()
    def open_model_dialog(self):
        if not self.current_folder:
            return self._run_js("alert('请先创建或选择一个对话')")
        is_enabled = bool(self._conv_model and self._conv_model.get("enabled", True))
        dialog = ModelConfigDialog(self.main_window, self._get_effective_platform(), self._get_effective_model(), is_enabled)
        if dialog.exec():
            if dialog.is_cleared():
                model_json = os.path.join(BASE_DIR, "records", self.current_folder, "model.json")
                if os.path.exists(model_json):
                    os.remove(model_json)
                self._conv_model = None
                self.client.reload_config()
                self._run_js(f"showModelTag({json.dumps(self.client.model)})")
            else:
                new_platform, new_model = dialog.get_values()
                cfg = {"platform": new_platform, "model": new_model, "enabled": dialog.is_enabled()}
                save_model_config(self.current_folder, cfg)
                self._conv_model = cfg
                if cfg["enabled"]:
                    self._run_js(f"showModelTag({json.dumps(new_model)})")
                else:
                    self.client.reload_config()
                    self._run_js(f"showModelTag({json.dumps(self.client.model)})")

    @Slot(result=str)
    def get_summary_content(self):
        if not self.current_folder:
            return ""
        summaries = load_memory_config(self.current_folder).get("summaries", [])
        if not summaries:
            return "暂无概括内容"
        return "\n\n".join([f"═══ 概括段 {i}（第 {s.get('round_start', 0)+1}-{s.get('round_end', 0)} 轮）═══\n{s['content']}" for i, s in enumerate(summaries, 1)])

    @Slot()
    def open_wallpaper_settings(self):
        is_bound = bool(load_wallpaper_config(self.current_folder)) if self.current_folder else False
        dialog = WallpaperDialog(self.main_window, self.client.config, is_bound)
        if dialog.exec():
            vals = dialog.get_values()
            if dialog.is_conversation_bound() and self.current_folder:
                save_wallpaper_config(self.current_folder, vals)
            else:
                self.client.config["wallpaper"] = vals
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.client.config, f, ensure_ascii=False, indent=2)
            url = QUrl.fromLocalFile(vals["path"]).toString() if vals["path"] else ""
            self._run_js(f"setWallpaper('{url}', {vals['opacity']})")
            self._run_js("onWallpaperSettingsClosed()")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YODER")
        self.resize(1200, 800)
        self.web_view = QWebEngineView()
        self.setCentralWidget(self.web_view)
        self.web_view.page().settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        self.channel = QWebChannel()
        self.bridge = Bridge(self.web_view, self)
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.web_view.load(QUrl.fromLocalFile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "template", "home.html")))
        self.web_view.loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok):
        if ok:
            QTimer.singleShot(1000, self._on_page_ready)

    def _on_page_ready(self):
        self.bridge.load_conversation_list()
        wp = self.bridge.client.config.get("wallpaper", {})
        if wp.get("path"):
            self.bridge._run_js(f"setWallpaper('{QUrl.fromLocalFile(wp['path']).toString()}', {wp.get('opacity', 0.2)})")


if __name__ == "__main__":
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-background-timer-throttling")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())