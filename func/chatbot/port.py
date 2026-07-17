import json
import os
from openai import OpenAI
from typing import Callable, Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")

class ChatClient:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config = self._load_config(config_path)
        self.api_keys = self.config.get("api_keys", {})
        self.model = self.config.get("model", "qwen3.7-max")
        self.max_tokens = self.config.get("max_tokens", 65536)
        self.thinking_level = self.config.get("thinking_level", "high")
        self.qwen_workspace_id = self.config.get("qwen_workspace_id", "")
        self._init_clients()

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            default_config = {
                "api_keys": {"deepseek_key": "", "qwen_key": ""},
                "model": "qwen3.7-max",
                "memory_rounds": 50,
                "thinking_level": "high",
                "max_tokens": 65536,
                "qwen_workspace_id": "",
                "wallpaper": {"path": "", "opacity": 0.2, "blur": 5}
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return default_config
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _init_clients(self):
        qwen_key = self.api_keys.get("qwen_key", "")
        deepseek_key = self.api_keys.get("deepseek_key", "")
        qwen_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.qwen_client = OpenAI(api_key=qwen_key, base_url=qwen_base) if qwen_key else None
        self.deepseek_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com") if deepseek_key else None

    def reload_config(self):
        self.config = self._load_config(CONFIG_PATH)
        self.api_keys = self.config.get("api_keys", {})
        self.model = self.config.get("model", "qwen3.7-max")
        self.max_tokens = self.config.get("max_tokens", 65536)
        self.thinking_level = self.config.get("thinking_level", "high")
        self.qwen_workspace_id = self.config.get("qwen_workspace_id", "")
        self._init_clients()

    def chat(self, messages, callback, stream=True):
        if self.model.startswith("qwen"):
            self._call_qwen(messages, callback, stream)
        elif self.model.startswith("deepseek"):
            self._call_deepseek(messages, callback, stream)
        else:
            callback("error", f"不支持的模型: {self.model}")

    def _call_qwen(self, messages, callback, stream):
        if not self.qwen_client:
            callback("error", "Qwen API Key 未配置")
            return
        try:
            completion = self.qwen_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                extra_body={"enable_thinking": True},
                stream=stream
            )
            has_started_content = False  # 标记是否已经开始输出正式内容
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                # 检查是否有思考内容
                if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    # 只有在还未开始输出正式内容时才输出思考
                    if not has_started_content:
                        callback("thinking", delta.reasoning_content)
                
                # 检查是否有正式内容
                if hasattr(delta, "content") and delta.content:
                    # 第一次出现正式内容时，标记已经开始
                    if not has_started_content:
                        has_started_content = True
                    callback("content", delta.content)
                    
        except Exception as e:
            callback("error", str(e))

    def _call_deepseek(self, messages, callback, stream):
        if not self.deepseek_client:
            callback("error", "DeepSeek API Key 未配置")
            return
        try:
            extra = {
                "thinking": {"type": "enabled"},
                "reasoning_effort": self.thinking_level
            }
            completion = self.deepseek_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                extra_body=extra,
                stream=stream
            )
            has_started_content = False  # 标记是否已经开始输出正式内容
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                # DeepSeek 的思考内容
                if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    if not has_started_content:
                        callback("thinking", delta.reasoning_content)
                
                # DeepSeek 的正式内容
                if hasattr(delta, "content") and delta.content:
                    if not has_started_content:
                        has_started_content = True
                    callback("content", delta.content)
                    
        except Exception as e:
            callback("error", str(e))