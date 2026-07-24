"""
agent_core.py - 思维链模式核心逻辑
实现三阶段流程: 规划 -> 逐文件分析 -> 综合总结
"""
import json
import re
import os
from typing import List, Dict, Optional, Callable

from openai import OpenAI

from .agent_prompts import (
    PLANNING_SYSTEM, PLANNING_USER,
    ANALYSIS_SYSTEM, ANALYSIS_USER,
    SUMMARY_SYSTEM, SUMMARY_USER,
)

# Agent 模式默认最大 token（由调用方传入）
DEFAULT_AGENT_MAX_TOKENS = 65536


def _read_file_safe(file_path: str, max_chars: int = 15000) -> str:
    """安全读取文件内容，限制大小"""
    try:
        if not os.path.isfile(file_path):
            return f"[文件不存在: {file_path}]"
        size = os.path.getsize(file_path)
        if size > 5 * 1024 * 1024:  # 5MB 以上跳过
            return f"[文件过大 ({size // 1024}KB)，已跳过: {os.path.basename(file_path)}]"
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n...[文件过大，仅展示前 {max_chars} 字]..."
        return content
    except Exception as e:
        return f"[读取文件失败: {os.path.basename(file_path)} - {e}]"


def _extract_json(text: str) -> Optional[Dict]:
    """从 AI 输出中提取 JSON"""
    try:
        return json.loads(text.strip())
    except:
        pass
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None


def _call_api(client: OpenAI, model: str, messages: list,
              callback: Optional[Callable] = None,
              thinking_callback: Optional[Callable] = None,
              stream: bool = True,
              extra_body: dict = None,
              max_tokens: int = DEFAULT_AGENT_MAX_TOKENS) -> str:
    """
    调用 AI API，支持流式和非流式。
    callback(type, content) 用于最终内容的流式输出。
    thinking_callback(content) 用于思考过程的流式输出（规划和推理内容）。
    返回完整文本。
    """
    if not stream or callback is None:
        completion = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens,
            stream=True,  # 总是用流式以获取思考内容
            extra_body=extra_body if extra_body else None
        )
        full_text = ""
        for chunk in completion:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                if thinking_callback:
                    thinking_callback(delta.reasoning_content)
            if hasattr(delta, "content") and delta.content:
                full_text += delta.content
        return full_text

    # 流式调用 - 支持思考和内容交错输出
    full_text = ""
    completion = client.chat.completions.create(
        model=model, messages=messages,
        max_tokens=max_tokens,
        stream=True,
        extra_body=extra_body if extra_body else None
    )
    for chunk in completion:
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


def _get_extra_body(platform: str, thinking_level: str = "high") -> dict:
    if platform == "阿里":
        return {"enable_thinking": True}
    elif platform in ("DeepSeek", "智谱"):
        return {"thinking": {"type": "enabled"}, "reasoning_effort": thinking_level}
    return {}


def _build_history_text(history: List[Dict], max_chars: int = 12000) -> str:
    """将对话历史格式化为可读文本，用于注入阶段3提示词"""
    if not history:
        return ""
    parts = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        # 保留系统消息（含记忆概括）
        if isinstance(content, list):
            # 多块内容（用户消息含文件）：取第一个文本块
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
        if len(text) > 3000:
            text = text[:3000] + "..."
        parts.append(f"{label}: {text}")
    result = "\n\n".join(parts)
    if len(result) > max_chars:
        result = result[-max_chars:]
    return result


def _build_phase12_history_text(history: List[Dict], max_chars: int = 3000) -> str:
    """为阶1/2构建简要历史（最近2轮），节省token"""
    if not history:
        return ""
    # 只取最近2轮（4条消息）
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
        if len(text) > 1500:
            text = text[:1500] + "..."
        parts.append(f"{label}: {text}")
    result = "\n\n".join(parts)
    if len(result) > max_chars:
        result = result[-max_chars:]
    return result


def run_agent_pipeline(
    client: OpenAI,
    model: str,
    platform: str,
    user_message: str,
    selected_files: List[str],
    root_path: str = "",
    thinking_level: str = "high",
    progress_callback: Callable = None,
    stream_callback: Callable = None,
    thinking_callback: Callable = None,
    history: List[Dict] = None,
    max_tokens: int = 65536,
):
    """
    执行完整的 Agent 流程:
    1. 规划阶段 - 生成任务列表
    2. 分析阶段 - 逐个任务分析文件
    3. 总结阶段 - 综合回答（注入对话历史作为上下文）

    progress_callback(status_str, tasklist_list) - 更新进度
    stream_callback(type, content) - 流式输出最终总结
    thinking_callback(content) - 流式输出规划和分析阶段的思考过程
    history - 对话历史（API 格式），注入阶1/2/3以支持多轮记忆
    """
    extra_body = _get_extra_body(platform, thinking_level)
    
    def _update_progress(status, tasks):
        if progress_callback:
            progress_callback(status, tasks)
    
    # ── 构建文件列表描述 ──
    file_list_text = ""
    file_map = {}
    for fpath in selected_files:
        basename = os.path.basename(fpath)
        relpath = os.path.relpath(fpath, root_path) if root_path else fpath
        file_list_text += f"- {relpath}\n"
        file_map[basename] = fpath
        file_map[relpath] = fpath
    
    if not file_list_text:
        file_list_text = "(未选择文件)"
    
    # ── 构建阶1/2简要历史 ──
    phase12_history = _build_phase12_history_text(history or [])
    
    # ═══ 阶 1: 规划 ═══
    _update_progress("📋 阶 1/3: 分析目标，制定任务计划...", [])
    
    phase1_user_content = PLANNING_USER.format(
        user_message=user_message,
        file_list=file_list_text
    )
    if phase12_history:
        phase1_user_content = (
            f"【对话历史】\n{phase12_history}\n\n"
            f"{phase1_user_content}"
        )
    
    plan_messages = [
        {"role": "system", "content": PLANNING_SYSTEM},
        {"role": "user", "content": phase1_user_content}
    ]

    # 包装回调：将模型所有输出（reasoning_content + content）都路由到思考块
    def _all_to_thinking(*args):
        """兼容 callback(type, text) 和 thinking_callback(text) 两种调用方式"""
        if len(args) == 2:
            # callback("content", text) 形式
            text = args[1]
        elif len(args) == 1:
            # thinking_callback(text) 形式
            text = args[0]
        else:
            return
        if thinking_callback:
            thinking_callback(text)

    # 规划阶段：阶段标记→内容块（可见），模型输出→思考块（折叠）
    phase12_max_tokens = max_tokens // 2  # 阶1/2使用配置的一半
    if stream_callback:
        stream_callback("content", "\n📋 【规划阶段】\n")
    plan_text = _call_api(
        client, model, plan_messages,
        callback=_all_to_thinking,  # content也路由到思考块
        thinking_callback=_all_to_thinking,  # reasoning_content也路由到思考块
        extra_body=None,
        max_tokens=phase12_max_tokens
    )
    plan = _extract_json(plan_text)

    if not plan or "tasks" not in plan:
        _update_progress("⚠️ 规划失败，切换为普通分析模式...", [])
        if stream_callback:
            stream_callback("content", "\n⚠️ 规划解析失败，切换为普通分析模式\n")
        
        fallback_user_content = ANALYSIS_USER.format(
            user_message=user_message,
            task_id=1,
            task_description=f"综合分析用户问题: {user_message}",
            file_contents=file_list_text,
            previous_results="(无前置分析)"
        )
        if phase12_history:
            fallback_user_content = (
                f"【对话历史】\n{phase12_history}\n\n"
                f"{fallback_user_content}"
            )
        
        fallback_messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user", "content": fallback_user_content}
        ]
        result = _call_api(client, model, fallback_messages,
                          callback=_all_to_thinking,
                          thinking_callback=_all_to_thinking,
                          extra_body=None,
                          max_tokens=phase12_max_tokens)
        _update_progress("", [])
        return result

    tasks = plan.get("tasks", [])
    task_results = []

    if stream_callback:
        goal = plan.get("goal", user_message)
        stream_callback("content", f"\n🎯 目标: {goal}\n📝 共 {len(tasks)} 个分析任务\n")

    # ═══ 阶段 2: 逐任务分析 ═══
    for i, task in enumerate(tasks):
        task_id = task.get("id", i + 1)
        task_desc = task.get("description", "")
        task_files = task.get("files", [])

        # 更新进度
        task_list_for_ui = []
        for j, t in enumerate(tasks):
            if j < i:
                task_list_for_ui.append({"text": t.get("description", ""), "status": "done"})
            elif j == i:
                task_list_for_ui.append({"text": t.get("description", ""), "status": "active"})
            else:
                task_list_for_ui.append({"text": t.get("description", ""), "status": "pending"})
        _update_progress(f"🔍 阶段 2/3: 正在分析任务 {task_id}/{len(tasks)}...", task_list_for_ui)

        # 读取相关文件
        file_contents = ""
        for fname in task_files:
            fpath = file_map.get(fname)
            if not fpath:
                for key, val in file_map.items():
                    if fname.lower() in key.lower():
                        fpath = val
                        break
            if fpath:
                content = _read_file_safe(fpath)
                file_contents += f"\n### 文件: {fname}\n```\n{content}\n```\n"
            else:
                file_contents += f"\n### 文件: {fname}\n[文件未找到]\n"

        if not file_contents:
            file_contents = "(此任务无需读取文件，或文件未找到)"

        # 构建前序任务结果上下文（关键改进：传递上下文以提高准确性）
        previous_results_text = "(无前置分析)"
        if task_results:
            previous_results_text = ""
            for tr in task_results:
                previous_results_text += f"\n### 任务 {tr['task_id']}: {tr['description']}\n{tr['result'][:3000]}\n"

        # 调用 AI 分析（包含用户问题上下文 + 前序任务结果 + 对话历史）
        analysis_user_content = ANALYSIS_USER.format(
            user_message=user_message,
            task_id=task_id,
            task_description=task_desc,
            file_contents=file_contents,
            previous_results=previous_results_text
        )
        if phase12_history:
            analysis_user_content = (
                f"【对话历史】\n{phase12_history}\n\n"
                f"{analysis_user_content}"
            )
        
        analysis_messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user", "content": analysis_user_content}
        ]

        if stream_callback:
            stream_callback("content", f"\n🔍 【分析任务 {task_id}/{len(tasks)}】{task_desc}\n")

        analysis_result = _call_api(
            client, model, analysis_messages,
            callback=_all_to_thinking,  # content也路由到思考块
            thinking_callback=_all_to_thinking,  # reasoning_content也路由到思考块
            extra_body=None,
            max_tokens=phase12_max_tokens
        )

        if stream_callback:
            stream_callback("content", f"\n✅ 任务 {task_id} 分析完成\n")

        task_results.append({
            "task_id": task_id,
            "description": task_desc,
            "result": analysis_result
        })

    # 更新所有任务为完成
    task_list_for_ui = [{"text": t.get("description", ""), "status": "done"} for t in tasks]
    _update_progress("📝 阶段 3/3: 综合分析结果，生成最终回答...", task_list_for_ui)

    if stream_callback:
        stream_callback("content", "\n📝 【总结阶段】正在综合分析所有任务结果...\n")

    # ═══ 阶段 3: 综合总结 ═══
    task_results_text = ""
    for tr in task_results:
        task_results_text += f"\n### 任务 {tr['task_id']}: {tr['description']}\n{tr['result']}\n"

    # 拼接对话历史到用户消息（仅阶段3，提供多轮上下文）
    history_text = _build_history_text(history or [])
    phase3_user_msg = user_message
    if history_text:
        phase3_user_msg = (
            f"【对话历史上下文】\n{history_text}\n\n"
            f"【当前问题】\n{user_message}"
        )

    summary_messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": SUMMARY_USER.format(
            user_message=phase3_user_msg,
            task_results=task_results_text
        )}
    ]

    # 总结阶段：流式输出最终回答到对话框
    # 不传thinking_callback，避免reasoning_content创建碎片化思考块
    final_result = _call_api(
        client, model, summary_messages,
        callback=stream_callback,
        thinking_callback=None,
        extra_body=extra_body,
        max_tokens=max_tokens  # 阶3使用完整 max_tokens
    )

    _update_progress("", [])
    return final_result
