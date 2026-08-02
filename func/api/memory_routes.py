"""
记忆概括路由（summarize、memory-config、memory）
"""
import json
import os

from fastapi import APIRouter, HTTPException

from func.api.config import BASE_DIR, get_config_dict
from func.api.models import SummarizeRequest, MemoryConfigModel
from func.chatbot.memory_manager import (
    load_memory_config, save_memory_config, _extract_dialogue, _count_rounds
)
from func.chatbot.tools_port_factory import ToolsPortFactory
from func.chatbot.message_build import load_conversation

router = APIRouter()


@router.post("/api/chats/{chat_id}/summarize")
async def summarize_chat(chat_id: str, request: SummarizeRequest = None):
    """手动概括对话：从标记位置开始，概括所有未概括的内容"""
    chat_file = os.path.join(BASE_DIR, "records", chat_id, "chat.json")
    if not os.path.exists(chat_file):
        raise HTTPException(status_code=404, detail="对话不存在")

    with open(chat_file, "r", encoding="utf-8") as f:
        messages = json.load(f)

    mem_cfg = load_memory_config(chat_id)
    max_chars = (request.max_chars if request else None) or mem_cfg.get("max_summary_chars", 2000)
    marker = mem_cfg.get("marker", 0)

    dialogue = _extract_dialogue(messages)
    total_rounds = _count_rounds(dialogue)

    if marker >= total_rounds:
        raise HTTPException(status_code=400, detail="没有需要概括的新对话")

    # 构建要概括的对话文本
    start_idx = marker * 2
    rounds_to_summarize = dialogue[start_idx:]

    if not rounds_to_summarize:
        raise HTTPException(status_code=400, detail="没有需要概括的新对话")

    conversation_text = ""
    for msg in rounds_to_summarize:
        role_label = "用户" if msg["role"] == "user" else "AI"
        if isinstance(msg["content"], list):
            parts = []
            for block in msg["content"]:
                if isinstance(block, dict) and "text" in block:
                    parts.append(block["text"])
            text = "\n".join(parts)
        else:
            text = str(msg["content"])
        conversation_text += f"\n{role_label}: {text}\n"

    # 获取之前的概括作为上下文
    prev_context = ""
    summaries = mem_cfg.get("summaries", [])
    if summaries:
        prev_parts = [s["content"] for s in summaries]
        prev_context = "\n\n之前的概括：\n" + "\n---\n".join(prev_parts)

    prompt = (
        f"请将以下对话内容概括为一段简洁的摘要，保留关键信息、决策和上下文。"
        f"概括字数控制在 {max_chars} 字以内。"
        f"直接输出概括内容，不要加任何前缀或说明。"
        f"{prev_context}"
    )

    summarize_messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": conversation_text}
    ]

    # 调用AI
    cfg = get_config_dict()
    platform = cfg.get("platform", "阿里")
    api_keys = cfg.get("api_keys", {})
    api_key = api_keys.get(platform, "")

    if not api_key:
        raise HTTPException(status_code=400, detail=f"{platform} API Key未配置")

    tools_port = ToolsPortFactory.create(platform=platform, api_key=api_key)
    result = tools_port.chat_with_tools(
        messages=summarize_messages, tools=[],
        callback=lambda et, d: None,
        model=cfg.get("model", "qwen-max")
    )

    summary_text = result["content"]

    # 保存概括
    summaries.append({
        "round_start": marker,
        "round_end": total_rounds,
        "content": summary_text
    })

    # 合并过多概括
    merge_every = mem_cfg.get("merge_every", 5)
    if len(summaries) >= merge_every:
        merged_content = "\n\n---\n\n".join(s["content"] for s in summaries)
        summaries = [{
            "round_start": summaries[0]["round_start"],
            "round_end": summaries[-1]["round_end"],
            "content": merged_content
        }]

    mem_cfg["summaries"] = summaries
    mem_cfg["marker"] = total_rounds
    save_memory_config(chat_id, mem_cfg)

    return {
        "status": "success",
        "summary": {
            "round_start": marker,
            "round_end": total_rounds,
            "content": summary_text
        },
        "total_summaries": len(summaries)
    }


@router.post("/api/chats/{chat_id}/memory-config")
async def save_memory_config_api(chat_id: str, cfg: MemoryConfigModel):
    """保存记忆概括配置"""
    mem_cfg = load_memory_config(chat_id)
    mem_cfg["enabled"] = cfg.enabled
    mem_cfg["max_summary_chars"] = cfg.max_summary_chars
    save_memory_config(chat_id, mem_cfg)
    return {"status": "success"}


@router.get("/api/chats/{chat_id}/memory")
async def get_chat_memory(chat_id: str):
    """获取对话记忆概括"""
    mem_cfg = load_memory_config(chat_id)
    summaries = mem_cfg.get("summaries", [])
    marker = mem_cfg.get("marker", 0)

    # 计算总轮数
    full_history = load_conversation(chat_id)
    dialogue = _extract_dialogue(full_history) if full_history else []
    total_rounds = _count_rounds(dialogue)

    return {
        "enabled": mem_cfg.get("enabled", False),
        "max_summary_chars": mem_cfg.get("max_summary_chars", 2000),
        "marker": marker,
        "total_rounds": total_rounds,
        "unsummarized_rounds": total_rounds - marker,
        "summaries": summaries
    }
