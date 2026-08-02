"""
对话管理路由（CRUD、历史、文件列表、对话级配置）
"""
import json
import os
import shutil
import time

from fastapi import APIRouter, HTTPException

from func.api.config import BASE_DIR, _stop_flags
from func.api.models import (
    CreateChatRequest, RenameChatRequest, ChatConfigModel, SaveFilesRequest
)
from func.chatbot.memory_manager import load_memory_config, save_memory_config
from func.files_reader.locate import get_file_tree

router = APIRouter()


# ──────────────────────────────────────────────
# 对话 CRUD
# ──────────────────────────────────────────────

@router.post("/api/chats")
async def create_chat(request: CreateChatRequest):
    """创建新对话"""
    chat_id = f"chat_{int(time.time())}"

    # 创建对话目录
    chat_dir = os.path.join(BASE_DIR, "records", chat_id)
    os.makedirs(chat_dir, exist_ok=True)

    # 初始化对话文件
    chat_file = os.path.join(chat_dir, "chat.json")
    with open(chat_file, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False)

    # 保存对话元数据（名称）
    meta_file = os.path.join(chat_dir, "meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"name": request.name}, f, ensure_ascii=False)

    return {"chat_id": chat_id, "name": request.name}


@router.get("/api/chats")
async def list_chats():
    """获取对话列表"""
    records_dir = os.path.join(BASE_DIR, "records")

    if not os.path.exists(records_dir):
        return []

    chats = []
    for item in os.listdir(records_dir):
        item_path = os.path.join(records_dir, item)
        if os.path.isdir(item_path):
            chat_file = os.path.join(item_path, "chat.json")
            if os.path.exists(chat_file):
                # 从meta.json读取名称，回退到目录名
                name = item
                meta_file = os.path.join(item_path, "meta.json")
                if os.path.exists(meta_file):
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        name = meta.get("name", item)
                    except Exception:
                        pass
                chats.append({
                    "id": item,
                    "name": name
                })

    return chats


@router.patch("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, request: RenameChatRequest):
    """重命名对话"""
    chat_dir = os.path.join(BASE_DIR, "records", chat_id)
    if not os.path.isdir(chat_dir):
        raise HTTPException(status_code=404, detail="对话不存在")

    meta_file = os.path.join(chat_dir, "meta.json")
    meta = {}
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    meta["name"] = request.name
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return {"status": "success", "name": request.name}


@router.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """删除对话"""
    chat_dir = os.path.join(BASE_DIR, "records", chat_id)
    if not os.path.isdir(chat_dir):
        raise HTTPException(status_code=404, detail="对话不存在")

    shutil.rmtree(chat_dir)
    return {"status": "success"}


# ──────────────────────────────────────────────
# 轮次删除
# ──────────────────────────────────────────────

@router.delete("/api/chats/{chat_id}/round/{round_index}")
async def delete_round(chat_id: str, round_index: int):
    """删除指定轮次的对话（一轮 = 一个user消息及其所有关联的assistant/tool消息）"""
    chat_file = os.path.join(BASE_DIR, "records", chat_id, "chat.json")
    if not os.path.exists(chat_file):
        raise HTTPException(status_code=404, detail="对话不存在")

    with open(chat_file, "r", encoding="utf-8") as f:
        messages = json.load(f)

    # 找到所有user消息的索引
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]

    if round_index < 0 or round_index >= len(user_indices):
        raise HTTPException(status_code=400, detail=f"无效的轮次索引: {round_index}，共{len(user_indices)}轮")

    start = user_indices[round_index]
    end = user_indices[round_index + 1] if round_index + 1 < len(user_indices) else len(messages)

    # 删除该轮所有消息
    del messages[start:end]

    # 调整记忆标记
    mem_cfg = load_memory_config(chat_id)
    marker = mem_cfg.get("marker", 0)
    if round_index < marker:
        mem_cfg["marker"] = max(0, marker - 1)
    # 调整summaries中的轮次引用
    for s in mem_cfg.get("summaries", []):
        if s.get("round_start", 0) > round_index:
            s["round_start"] = max(0, s["round_start"] - 1)
        if s.get("round_end", 0) > round_index:
            s["round_end"] = max(0, s["round_end"] - 1)
    # 清理无效概括（start >= end）
    mem_cfg["summaries"] = [s for s in mem_cfg.get("summaries", []) if s.get("round_start", 0) < s.get("round_end", 0)]

    save_memory_config(chat_id, mem_cfg)

    with open(chat_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    return {"status": "success", "deleted_round": round_index}


# ──────────────────────────────────────────────
# 对话历史
# ──────────────────────────────────────────────

@router.get("/api/chats/{chat_id}/history")
async def get_chat_history(chat_id: str):
    """获取对话历史"""
    chat_file = os.path.join(BASE_DIR, "records", chat_id, "chat.json")
    if os.path.exists(chat_file):
        with open(chat_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ──────────────────────────────────────────────
# 对话级配置
# ──────────────────────────────────────────────

@router.get("/api/chats/{chat_id}/config")
async def get_chat_config(chat_id: str):
    """获取对话级配置覆盖"""
    config_path = os.path.join(BASE_DIR, "records", chat_id, "model.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@router.post("/api/chats/{chat_id}/config")
async def save_chat_config(chat_id: str, cfg: ChatConfigModel):
    """保存对话级配置覆盖到records"""
    chat_dir = os.path.join(BASE_DIR, "records", chat_id)
    os.makedirs(chat_dir, exist_ok=True)

    config_path = os.path.join(chat_dir, "model.json")
    data = {k: v for k, v in cfg.dict().items() if v is not None}

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"status": "success"}


# ──────────────────────────────────────────────
# 文件列表持久化
# ──────────────────────────────────────────────

@router.post("/api/chats/{chat_id}/files")
async def save_files(chat_id: str, request: SaveFilesRequest):
    """保存文件列表路径到对话记录（仅保存根目录路径）"""
    chat_dir = os.path.join(BASE_DIR, "records", chat_id)
    os.makedirs(chat_dir, exist_ok=True)
    files_path = os.path.join(chat_dir, "files.json")
    with open(files_path, "w", encoding="utf-8") as f:
        json.dump({"path": request.path}, f, ensure_ascii=False)
    return {"status": "success"}


@router.get("/api/chats/{chat_id}/files")
async def get_files(chat_id: str):
    """获取已保存的文件列表"""
    files_path = os.path.join(BASE_DIR, "records", chat_id, "files.json")
    if os.path.exists(files_path):
        with open(files_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"path": "", "tree": []}


@router.delete("/api/chats/{chat_id}/files")
async def clear_files(chat_id: str):
    """清除已保存的文件列表"""
    files_path = os.path.join(BASE_DIR, "records", chat_id, "files.json")
    if os.path.exists(files_path):
        os.remove(files_path)
    return {"status": "success"}


# ──────────────────────────────────────────────
# 文件夹树加载
# ──────────────────────────────────────────────

@router.get("/api/files")
async def load_files(path: str):
    """加载文件夹树"""
    try:
        tree = get_file_tree(path)
        return {"status": "success", "tree": tree}
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail=f"{path} 不是有效目录")
    except PermissionError:
        raise HTTPException(status_code=403, detail="无权限访问该目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
