"""
api_caller.py - 共享的 API 调用工具
封装 OpenAI 流式调用，支持 thinking 和 content 双通道回调。
"""
from typing import Optional, Callable
from openai import OpenAI

DEFAULT_MAX_TOKENS = 65536


class UserStoppedError(Exception):
    """用户主动停止生成时抛出的异常，用于穿透所有阶段并在管线顶层捕获"""
    pass


def call_api(
    client: OpenAI,
    model: str,
    messages: list,
    callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    extra_body: dict = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.7,
    stop_check: Optional[Callable] = None,
) -> str:
    """
    调用 AI API（流式）。

    Args:
        client: OpenAI 客户端
        model: 模型名称
        messages: 消息列表
        callback: (type, content) 内容流式回调
        thinking_callback: (content,) 思考流式回调
        extra_body: 额外请求体参数
        max_tokens: 最大 token 数
        temperature: 温度
        stop_check: 停止检查回调，返回 True 时中止流式输出（保留已生成内容）

    Returns:
        完整文本
    """
    full_text = ""
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
        extra_body=extra_body if extra_body else None,
    )
    for chunk in completion:
        # 检查用户是否请求停止 —— 抛出异常穿透所有阶段，由管线顶层捕获
        if stop_check and stop_check():
            raise UserStoppedError()
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
            if thinking_callback:
                thinking_callback(delta.reasoning_content)
        if hasattr(delta, "content") and delta.content:
            full_text += delta.content
            if callback:
                callback("content", delta.content)
    return full_text


def get_extra_body(platform: str, thinking_level: str = "high") -> dict:
    """根据平台返回额外的请求体参数"""
    if platform == "阿里":
        return {"enable_thinking": True}
    elif platform == "DeepSeek":
        return {"thinking": {"type": "enabled"}, "reasoning_effort": thinking_level}
    elif platform == "智谱":
        return {"thinking": {"type": "enabled"}}
    return {}
