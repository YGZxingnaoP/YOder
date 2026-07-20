import json
import os
from openai import OpenAI
from typing import Callable, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")

PLATFORM_MODELS = {
    "阿里": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-max", "qwen3.7-max", "qwen3.7-plus"],
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner"],
    "智谱": ["glm-4-plus", "glm-4-long", "glm-4-flash", "glm-5.2"],
}

PLATFORM_BASE_URLS = {
    "阿里": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "DeepSeek": "https://api.deepseek.com",
    "智谱": "https://open.bigmodel.cn/api/paas/v4/",
}

def summarize_chat(messages: list, config: dict) -> str:
    """
    非流式 chat 调用, 用于后台记忆概括。
    config 需包含: api_keys, platform, model, max_tokens
    """
    keys = config.get("api_keys", {})
    platform = config.get("platform", "阿里")
    model = config.get("model", "qwen-max")
    max_tokens = config.get("max_tokens", 65536)
    base_url = PLATFORM_BASE_URLS.get(platform, "")
    key = keys.get(platform, "")
    if not key or not base_url:
        raise ValueError(f"{platform} API Key 未配置")
    client = OpenAI(api_key=key, base_url=base_url)
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        stream=False
    )
    if completion.choices and completion.choices[0].message.content:
        return completion.choices[0].message.content
    return ""


class ChatClient:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config = self._load_config(config_path)
        self.platform = self.config.get("platform", "阿里")
        self.model = self.config.get("model", "qwen-max")
        self.max_tokens = self.config.get("max_tokens", 65536)
        self.thinking_level = self.config.get("thinking_level", "high")
        self._init_clients()

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            default_config = {
                "api_keys": {"阿里": "", "DeepSeek": "", "智谱": ""},
                "platform": "阿里",
                "model": "qwen-max",
                "memory_rounds": 50,
                "thinking_level": "high",
                "max_tokens": 65536,
                "wallpaper": {"path": "", "opacity": 0.2}
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return default_config
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _init_clients(self):
        keys = self.config.get("api_keys", {})
        self._clients = {}
        for platform, base_url in PLATFORM_BASE_URLS.items():
            key = keys.get(platform, "")
            if key:
                self._clients[platform] = OpenAI(api_key=key, base_url=base_url)

    def reload_config(self):
        self.config = self._load_config(CONFIG_PATH)
        self.platform = self.config.get("platform", "阿里")
        self.model = self.config.get("model", "qwen-max")
        self.max_tokens = self.config.get("max_tokens", 65536)
        self.thinking_level = self.config.get("thinking_level", "high")
        self._init_clients()

    def chat(self, messages, callback, stream=True):
        client = self._clients.get(self.platform)
        if not client:
            callback("error", f"{self.platform} API Key 未配置")
            return
        try:
            extra_body = self._get_extra_body()
            completion = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                extra_body=extra_body if extra_body else None,
                stream=stream
            )
            has_started_content = False
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    if not has_started_content:
                        callback("thinking", delta.reasoning_content)
                if hasattr(delta, "content") and delta.content:
                    if not has_started_content:
                        has_started_content = True
                    callback("content", delta.content)
        except Exception as e:
            callback("error", str(e))

    def chat_with_model(self, messages, callback, platform=None, model=None, stream=True):
        """使用指定的平台和模型进行 chat 调用"""
        client = self._clients.get(platform)
        if not client:
            callback("error", f"{platform} API Key 未配置")
            return
        try:
            extra_body = self._get_extra_body_for(platform)
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=self.max_tokens,
                extra_body=extra_body if extra_body else None,
                stream=stream
            )
            has_started_content = False
            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    if not has_started_content:
                        callback("thinking", delta.reasoning_content)
                if hasattr(delta, "content") and delta.content:
                    if not has_started_content:
                        has_started_content = True
                    callback("content", delta.content)
        except Exception as e:
            callback("error", str(e))

    def _get_extra_body_for(self, platform):
        if platform == "阿里":
            return {"enable_thinking": True}
        elif platform == "DeepSeek":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": self.thinking_level}
        elif platform == "智谱":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": self.thinking_level}
        return None

    def _get_extra_body(self):
        return self._get_extra_body_for(self.platform)
