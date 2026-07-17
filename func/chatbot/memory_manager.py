"""
chatbot/memory_manager.py
读取当前对话记录，按轮数截取最近的历史，用于构建长期记忆。
"""
import os
from typing import List, Dict
from .message_build import load_conversation

def load_memory(folder_name: str, num_rounds: int = 50) -> List[Dict]:
    """
    返回最近 num_rounds 轮 user-assistant 对话对，拼接为消息列表。
    不包含 system 消息。
    如果记录不存在或不足，返回实际内容。
    """
    full_history = load_conversation(folder_name)
    if not full_history:
        return []

    # 过滤掉 system 消息，只保留 user 和 assistant
    dialogue = [msg for msg in full_history if msg["role"] in ("user", "assistant")]

    # 获取最近 2*num_rounds 条消息（每轮包含 user 和 assistant）
    max_msgs = num_rounds * 2
    recent = dialogue[-max_msgs:] if len(dialogue) > max_msgs else dialogue

    # 清理非标准字段，并将 UI 专用的 file_content 封装为 API 支持的 text 格式
    clean_recent = []
    for msg in recent:
        content = msg.get("content", "")
        if isinstance(content, list):
            api_content = []
            for block in content:
                b_type = block.get("type")
                if b_type == "file_content":
                    # 将文件内容封装为纯文本，避免 API 报错，同时保留文件信息供模型参考
                    file_name = block.get("file_name", "unknown")
                    file_path = block.get("file_path", "")
                    file_text = block.get("text", "")
                    text_for_api = (
                        f"[文件名称: {file_name}]\n"
                        f"[文件位置: {file_path}]\n"
                        f"--- 文件内容开始 ---\n{file_text}\n--- 文件内容结束 ---"
                    )
                    api_content.append({"type": "text", "text": text_for_api})
                elif b_type == "text":
                    api_content.append({"type": "text", "text": block.get("text", "")})
                elif b_type == "image_url":
                    api_content.append(block)
                else:
                    api_content.append({"type": "text", "text": str(block)})
            clean_recent.append({"role": msg["role"], "content": api_content})
        else:
            clean_recent.append({"role": msg["role"], "content": content})

    return clean_recent