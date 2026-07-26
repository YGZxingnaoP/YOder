"""
phase2_filler.py - 阶段二：大框架内容填充
逐个处理 task，填充 [task_n] 占位符。
AI 可发起子任务创建（[task1_1]、[task1_2]）。
"""
import json
import os
import re
from typing import Optional, Callable

from .api_caller import call_api, get_extra_body, UserStoppedError
from .file_reader import read_file_full, resolve_file, build_file_map
from .output_manager import OutputManager
from .task_manager import build_task_order, build_tasklist_for_ui, mark_task_active
from ..agent_prompts import PHASE2_FILLER_SYSTEM, PHASE2_FILLER_USER
from ..taskprests.presets import get_preset


class Phase2Result:
    """阶段二执行结果"""
    def __init__(self):
        self.all_filled = True      # 所有 task 都成功填充
        self.failed_tasks = []      # 填充失败的 task_id 列表
        self.subtask_creations = [] # [(parent_id, [subtask_ids])] 记录子任务创建


def run_phase2(
    client,
    model: str,
    platform: str,
    user_message: str,
    selected_files: list,
    root_path: str,
    history_text: str,
    system_prompt: str,
    output_mgr: OutputManager,
    thinking_level: str = "high",
    max_tokens: int = 65536,
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    stop_check: Optional[Callable] = None,
) -> Phase2Result:
    """
    执行阶段二：逐个填充 task 内容。

    Args:
        output_mgr: 阶段一创建的 OutputManager 实例
        ...: 标准 Agent 参数

    Returns:
        Phase2Result
    """
    result = Phase2Result()
    extra_body = get_extra_body(platform, thinking_level)

    # ── 构建文件映射 ──
    file_list_text, file_map = build_file_map(selected_files, root_path)

    # ── 获取初始 task 列表 ──
    tasks = output_mgr.get_all_tasks()
    task_order = build_task_order(tasks)

    if progress_callback:
        tasklist = build_tasklist_for_ui(tasks)
        progress_callback("阶段二：开始填充任务", tasklist)

    processed = set()  # 已处理的 task_id

    # ── 逐个处理 task ──
    while True:
        # 重新获取最新 task 列表（可能新增子任务）
        tasks = output_mgr.get_all_tasks()
        task_order = build_task_order(tasks)

        # 找到下一个 pending 的 task
        next_tid = None
        for tid in task_order:
            if tid not in processed and tasks[tid].get("status") == "pending":
                next_tid = tid
                break

        if next_tid is None:
            break  # 没有更多 pending task

        # 用户停止检查：在每个 task 开始前检查，避免不必要的工作
        if stop_check and stop_check():
            raise UserStoppedError()

        tid = next_tid
        task = tasks[tid]
        processed.add(tid)

        # ── 更新 UI：标记当前 task 为 active ──
        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            mark_task_active(tasklist, tid)
            progress_callback(f"阶段二：正在填充 {tid}", tasklist)

        # ── 读取任务相关文件（无截断） ──
        task_files = task.get("files", [])
        file_contents = ""
        for fname in task_files:
            fpath = resolve_file(fname, file_map)
            if fpath:
                content = read_file_full(fpath)
                relpath = os.path.relpath(fpath, root_path) if root_path else fpath
                file_contents += f"\n### 文件: {relpath}\n```\n{content}\n```\n"
            else:
                file_contents += f"\n### 文件: {fname}\n[文件未找到]\n"

        if not file_contents:
            file_contents = "(此任务无关联文件)"

        # ── 构建当前 task 在框架中的上下文 ──
        framework = output_mgr.get_framework()
        task_context = _extract_task_context(framework, tid)

        # ── 构造系统消息（注入预设约束） ──
        sys_msg = PHASE2_FILLER_SYSTEM
        if system_prompt:
            sys_msg = f"{system_prompt}\n\n---\n\n{sys_msg}"

        # 加载并注入该 task 对应的输出格式预设
        preset_name = task.get("preset", "mixed")
        preset_content = get_preset(preset_name)
        sys_msg = f"{sys_msg}\n{preset_content}"

        # ── 构造用户消息 ──
        review_feedback = task.get("review_feedback", "")
        user_msg = PHASE2_FILLER_USER.format(
            user_message=user_message,
            task_id=tid,
            task_description=task.get("description", ""),
            task_requirements=task.get("requirements", "按任务描述完成即可"),
            task_context=task_context,
            file_contents=file_contents,
            framework_snippet=_get_framework_snippet(framework, tid),
            history=history_text,
            review_feedback=review_feedback if review_feedback else "(无，首次填充)",
            principle=output_mgr.get_principle_text(),
        )

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]

        # ── 命名思考块回调 ──
        think_name = f"{tid}思考内容"

        def _make_think_cb(name):
            def _cb(content):
                if thinking_callback:
                    thinking_callback(content)
            return _cb

        think_cb = _make_think_cb(think_name)

        # ── 流式回调：task 内容通过 fold 块输出，不污染最终 content ──
        fold_name = f"{tid}输出"

        def _task_stream(type_, content):
            if stream_callback:
                if type_ == "content":
                    # 重定向到 fold 块
                    stream_callback(f"fold:{fold_name}", content)
                else:
                    stream_callback(type_, content)

        task_response = call_api(
            client, model, messages,
            callback=_task_stream,
            thinking_callback=think_cb,
            extra_body=extra_body,
            max_tokens=max_tokens,
            temperature=temperature,
            stop_check=stop_check,
        )

        # ── 解析输出 ──
        fill_content, new_subtasks = _parse_fill_output(task_response, tid)

        # ── 处理子任务创建 ──
        if new_subtasks:
            for sub_tid, sub_data in new_subtasks.items():
                output_mgr.add_subtask(
                    parent_id=tid,
                    subtask_id=sub_tid,
                    description=sub_data.get("description", ""),
                    files=sub_data.get("files", []),
                    requirements=sub_data.get("requirements", ""),
                )
            result.subtask_creations.append((tid, list(new_subtasks.keys())))

            # 不填充当前 task（它被拆分为子任务了），重新进入循环处理子任务
            # 标记当前 task 为 filled（其内容在框架中由子任务占位）
            sub_placeholder = "\n".join(f"[{st}]" for st in new_subtasks.keys())
            output_mgr.fill_task(tid, sub_placeholder)

            # 更新 UI tasklist
            if progress_callback:
                tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
                progress_callback(f"阶段二：{tid} 拆分为子任务", tasklist)
        else:
            # ── 正常填充 ──
            if fill_content.strip():
                output_mgr.fill_task(tid, fill_content)
            else:
                output_mgr.update_task(tid, status="error", review_feedback="输出为空")
                result.failed_tasks.append(tid)
                result.all_filled = False

        # ── 每完成一个 task 更新 UI ──
        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback("阶段二：任务填充进行中", tasklist)

    # ── 阶段二完成 ──
    if progress_callback:
        tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
        progress_callback("阶段二完成：所有任务填充完毕", tasklist)

    return result


def _extract_task_context(framework: str, task_id: str) -> str:
    """
    从框架中提取 task 的完整上下文，
    帮助 AI 理解此 task 在整体结构中的位置。
    不截断，返回完整框架。
    """
    placeholder = f"[{task_id}]"
    idx = framework.find(placeholder)
    if idx == -1:
        return "(无法定位该任务在框架中的位置)"
    return framework


def _get_framework_snippet(framework: str, task_id: str) -> str:
    """获取完整框架内容"""
    return framework


def _parse_fill_output(response: str, parent_tid: str) -> tuple:
    """
    解析阶段二的 task 填充输出。

    AI 可能输出：
    1. 直接内容文本（填充到 [task_n]）
    2. JSON（含 content 和可能的 subtasks）

    子任务格式（JSON）：
    {
        "content": "此 task 被拆分，内容为子任务占位说明",
        "subtasks": {
            "task1_1": {
                "description": "子任务1描述",
                "files": ["相关文件"],
                "requirements": "子任务要求"
            },
            "task1_2": {
                "description": "子任务2描述",
                "files": ["相关文件"],
                "requirements": "子任务要求"
            }
        }
    }

    Returns:
        (fill_content, new_subtasks_dict)
    """
    new_subtasks = {}

    # 尝试 JSON 解析
    json_data = _extract_json(response)
    if json_data and isinstance(json_data, dict):
        content = json_data.get("content", "")
        subtasks = json_data.get("subtasks", {})
        if subtasks:
            for sub_tid, sub_data in subtasks.items():
                new_subtasks[sub_tid.lower()] = {
                    "description": sub_data.get("description", ""),
                    "files": sub_data.get("files", []),
                    "requirements": sub_data.get("requirements", ""),
                }
            return content, new_subtasks
        # 有 JSON 但没有 subtasks，content 就是填充内容
        if content:
            return content, new_subtasks

    # 纯文本输出（最常见的情况）
    # 检查是否有 [SUBTASKS] 标记
    subtask_match = re.search(
        r'\[SUBTASKS\]\s*```(?:json)?\s*\n?(.*?)\n?\s*```',
        response, re.DOTALL
    )
    if subtask_match:
        try:
            subtasks_data = json.loads(subtask_match.group(1).strip())
            for sub_tid, sub_data in subtasks_data.items():
                new_subtasks[sub_tid.lower()] = {
                    "description": sub_data.get("description", ""),
                    "files": sub_data.get("files", []),
                    "requirements": sub_data.get("requirements", ""),
                }
            # 子任务标记前的文本作为父 task 内容
            content = response[:subtask_match.start()].strip()
            return content, new_subtasks
        except:
            pass

    # 纯文本直接返回
    return response.strip(), new_subtasks


def _extract_json(text: str) -> Optional[dict]:
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
    return None
