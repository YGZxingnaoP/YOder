"""
chatbot/memory_manager.py
记忆概括管理模块：
- 对话级记忆配置 (memory.json)
- 对话级模型配置 (model.json)
- 对话级壁纸配置 (wallpaper.json)
- 记忆概括构建与存储
"""
import os
import json
from typing import List, Dict, Optional

from .message_build import load_conversation, RECORDS_DIR

# ── 默认配置 ──
DEFAULT_MEMORY_CONFIG = {
    "enabled": False,
    "summarize_after": 10,
    "max_summary_chars": 2000,
    "merge_every": 5,
    "summaries": []
}

# ═══════════════════════════════════════════════════
#  对话级配置读写
# ═══════════════════════════════════════════════════

def _conv_dir(folder_name: str) -> str:
    return os.path.join(RECORDS_DIR, folder_name)


def load_memory_config(folder_name: str) -> Dict:
    """加载对话的记忆概括配置"""
    path = os.path.join(_conv_dir(folder_name), "memory.json")
    if not os.path.exists(path):
        return dict(DEFAULT_MEMORY_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # 确保字段完整
        for k, v in DEFAULT_MEMORY_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return dict(DEFAULT_MEMORY_CONFIG)


def save_memory_config(folder_name: str, config: Dict):
    """保存对话的记忆概括配置"""
    d = _conv_dir(folder_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "memory.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_model_config(folder_name: str) -> Optional[Dict]:
    """加载对话绑定的模型, 返回 None 表示未绑定"""
    path = os.path.join(_conv_dir(folder_name), "model.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_model_config(folder_name: str, config: Dict):
    d = _conv_dir(folder_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "model.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_wallpaper_config(folder_name: str) -> Optional[Dict]:
    """加载对话绑定的壁纸, 返回 None 表示未绑定"""
    path = os.path.join(_conv_dir(folder_name), "wallpaper.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_wallpaper_config(folder_name: str, config: Dict):
    d = _conv_dir(folder_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "wallpaper.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════
#  内部工具
# ═══════════════════════════════════════════════════

def _extract_dialogue(messages: List[Dict]) -> List[Dict]:
    """从 chat.json 消息列表中提取 user/assistant 轮次, 转为 API 格式"""
    pairs = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            api_content = []
            for block in content:
                b_type = block.get("type")
                if b_type == "file_content":
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
            pairs.append({"role": role, "content": api_content})
        else:
            pairs.append({"role": role, "content": content})
    return pairs


def _count_rounds(dialogue: List[Dict]) -> int:
    """计算对话轮数 (每对 user+assistant 算一轮)"""
    user_count = sum(1 for m in dialogue if m["role"] == "user")
    assistant_count = sum(1 for m in dialogue if m["role"] == "assistant")
    return min(user_count, assistant_count)


# ═══════════════════════════════════════════════════
#  记忆构建 (发送给 AI 时使用)
# ═══════════════════════════════════════════════════

def load_memory(folder_name: str, num_rounds: int = 50,
                force_use_summary: bool = False) -> List[Dict]:
    """
    构建发送给 AI 的历史消息列表。

    - 默认模式: 如果对话轮数 <= num_rounds, 直接返回原始对话
    - 记忆模式: 超出 num_rounds 或 force_use_summary=True 时,
      用概括替代较早的轮次, 仅保留最近 num_rounds 轮原始对话
    """
    full_history = load_conversation(folder_name)
    if not full_history:
        return []

    dialogue = _extract_dialogue(full_history)
    if not dialogue:
        return []

    total_rounds = _count_rounds(dialogue)

    # 对话轮数未超限 且 未强制使用 → 直接返回原始对话
    if total_rounds <= num_rounds and not force_use_summary:
        return dialogue[-(num_rounds * 2):]

    # ── 使用概括 ──
    mem_cfg = load_memory_config(folder_name)
    summaries = mem_cfg.get("summaries", [])

    if not summaries:
        # 无可用概括, 退化为截取最近轮次
        return dialogue[-(num_rounds * 2):]

    # 合并所有概括为一条上下文
    summary_parts = []
    for s in summaries:
        summary_parts.append(s["content"])
    combined = "\n\n---\n\n".join(summary_parts)

    summary_msg = {
        "role": "system",
        "content": (
            "以下是之前对话的概括记录，供你参考上下文：\n\n"
            + combined
        )
    }

    # 最近 num_rounds 轮的原始消息
    recent = dialogue[-(num_rounds * 2):]

    return [summary_msg] + recent


# ═══════════════════════════════════════════════════
#  概括触发判断
# ═══════════════════════════════════════════════════

def should_trigger_summarize(folder_name: str) -> bool:
    """
    判断是否应触发新的概括。
    当未概括的轮次数 >= summarize_after 时返回 True。
    """
    mem_cfg = load_memory_config(folder_name)
    if not mem_cfg.get("enabled", False):
        return False

    full_history = load_conversation(folder_name)
    if not full_history:
        return False

    dialogue = _extract_dialogue(full_history)
    total_rounds = _count_rounds(dialogue)

    # 已概括覆盖到的轮次
    summaries = mem_cfg.get("summaries", [])
    max_covered = 0
    for s in summaries:
        re = s.get("round_end", 0)
        if re > max_covered:
            max_covered = re

    unsummarized = total_rounds - max_covered
    return unsummarized >= mem_cfg.get("summarize_after", 10)


# ═══════════════════════════════════════════════════
#  概括 Prompt 构建
# ═══════════════════════════════════════════════════

def build_summarize_messages(folder_name: str) -> Optional[List[Dict]]:
    """
    构建用于调用 AI 概括的 messages 列表。
    如果无需概括则返回 None。
    """
    mem_cfg = load_memory_config(folder_name)
    if not mem_cfg.get("enabled", False):
        return None

    full_history = load_conversation(folder_name)
    if not full_history:
        return None

    dialogue = _extract_dialogue(full_history)
    total_rounds = _count_rounds(dialogue)

    summaries = mem_cfg.get("summaries", [])
    max_covered = 0
    for s in summaries:
        re = s.get("round_end", 0)
        if re > max_covered:
            max_covered = re

    unsummarized = total_rounds - max_covered
    if unsummarized < mem_cfg.get("summarize_after", 10):
        return None

    # 截取需要概括的轮次
    start_round = max_covered
    start_idx = start_round * 2
    end_idx = start_idx + mem_cfg.get("summarize_after", 10) * 2
    rounds_to_summarize = dialogue[start_idx:end_idx]

    if not rounds_to_summarize:
        return None

    max_chars = mem_cfg.get("max_summary_chars", 2000)

    # 如果已有之前的概括, 作为上下文传入
    prev_context = ""
    if summaries:
        prev_parts = [s["content"] for s in summaries]
        prev_context = "\n\n之前的概括：\n" + "\n---\n".join(prev_parts)

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

    prompt = (
        f"请将以下对话内容概括为一段简洁的摘要，保留关键信息、决策和上下文。"
        f"概括字数控制在 {max_chars} 字以内。"
        f"直接输出概括内容，不要加任何前缀或说明。"
        f"{prev_context}"
    )

    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": conversation_text}
    ]


# ═══════════════════════════════════════════════════
#  概括结果存储
# ═══════════════════════════════════════════════════

def save_summary(folder_name: str, summary_text: str):
    """将新的概括结果存入 memory.json, 必要时触发合并"""
    mem_cfg = load_memory_config(folder_name)
    summaries = mem_cfg.get("summaries", [])

    full_history = load_conversation(folder_name)
    dialogue = _extract_dialogue(full_history) if full_history else []
    total_rounds = _count_rounds(dialogue)

    # 计算本轮概括的覆盖范围
    max_covered = 0
    for s in summaries:
        re = s.get("round_end", 0)
        if re > max_covered:
            max_covered = re

    new_end = min(max_covered + mem_cfg.get("summarize_after", 10), total_rounds)

    summaries.append({
        "round_start": max_covered,
        "round_end": new_end,
        "content": summary_text
    })

    # 检查是否需要合并
    merge_every = mem_cfg.get("merge_every", 5)
    if len(summaries) >= merge_every:
        merged_content = "\n\n---\n\n".join(s["content"] for s in summaries)
        summaries = [{
            "round_start": summaries[0]["round_start"],
            "round_end": summaries[-1]["round_end"],
            "content": merged_content
        }]

    mem_cfg["summaries"] = summaries
    save_memory_config(folder_name, mem_cfg)
