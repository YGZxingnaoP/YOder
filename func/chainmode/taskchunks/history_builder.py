"""
history_builder.py - 对话历史格式化工具
将对话历史格式化为可读文本，用于注入各阶段提示词。
不做任何截断，保证 AI 获得完整的上下文信息。
"""
from typing import List, Dict


def build_history_text(history: List[Dict]) -> str:
    """
    将对话历史格式化为可读文本（阶段3/4使用，较完整）。
    不截断任何内容，完整传递历史信息。
    """
    if not history:
        return ""
    parts = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"]
                    break
            else:
                text = ""
        else:
            text = str(content) if content else ""
        if not text.strip():
            continue
        label = "用户" if role == "user" else "助手"
        parts.append(f"{label}: {text}")
    return "\n\n".join(parts)


def build_brief_history(history: List[Dict]) -> str:
    """
    为阶段1/2构建简要历史（最近2轮）。
    仅取最近4条消息，但不截断每条消息的内容。
    """
    if not history:
        return ""
    recent = history[-4:]
    parts = []
    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"]
                    break
            else:
                text = ""
        else:
            text = str(content) if content else ""
        if not text.strip():
            continue
        label = "用户" if role == "user" else "助手"
        parts.append(f"{label}: {text}")
    return "\n\n".join(parts)
