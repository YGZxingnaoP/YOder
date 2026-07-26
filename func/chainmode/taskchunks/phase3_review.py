"""
phase3_review.py - 阶段三：完整格式和内容审查
审查最终 output.json，若有问题则指定 task 重做（重回阶段二）。
最多 6 次审查。仅审查父级 task。
"""
import json
import os
import re
from typing import Optional, Callable

from .api_caller import call_api, get_extra_body
from .output_manager import OutputManager
from .task_manager import build_tasklist_for_ui
from ..agent_prompts import PHASE3_REVIEW_SYSTEM, PHASE3_REVIEW_USER

MAX_REVIEW_ATTEMPTS = 6


class Phase3Result:
    """阶段三执行结果"""
    def __init__(self):
        self.passed = False           # 审查是否通过
        self.review_count = 0         # 审查次数
        self.redone_tasks = []        # 被重做的 task_id 列表
        self.final_feedback = ""      # 最后一次审查反馈


def run_phase3(
    client,
    model: str,
    platform: str,
    user_message: str,
    selected_files: list,
    root_path: str,
    system_prompt: str,
    output_mgr: OutputManager,
    thinking_level: str = "high",
    max_tokens: int = 65536,
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    phase2_runner: Optional[Callable] = None,
    coordinated_runner: Optional[Callable] = None,
    stop_check: Optional[Callable] = None,
) -> Phase3Result:
    """
    执行阶段三：审查最终输出。

    Args:
        output_mgr: 阶段二完成后的 OutputManager
        phase2_runner: 回调函数，用于重做指定 task。
                       签名: phase2_runner(task_id, sibling_context="", associated_tasks=None) -> bool
                       返回 True 表示重做成功。
                       associated_tasks 是审查 AI 识别出的与该 task 关联的 task_id 列表，
                       其内容会被注入到重做提示词中。
        coordinated_runner: 协调重做回调，用于多次失败后的批量重做。
                       签名: coordinated_runner(failed_task_ids, feedback) -> bool

    Returns:
        Phase3Result
    """
    result = Phase3Result()
    extra_body = get_extra_body(platform, thinking_level)

    # ── 构建文件路径列表（仅路径，不含内容） ──
    file_paths_text = ""
    for fpath in selected_files:
        relpath = os.path.relpath(fpath, root_path) if root_path else fpath
        file_paths_text += f"- {relpath}\n"
    if not file_paths_text:
        file_paths_text = "(未选择文件)"

    previous_feedback = ""

    for attempt in range(1, MAX_REVIEW_ATTEMPTS + 1):
        result.review_count = attempt

        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback(f"阶段三：第 {attempt} 次审查", tasklist)

        # ── 构建审查消息 ──
        tasks = output_mgr.get_all_tasks()

        # 仅审查父级 task
        parent_tasks = {}
        for tid, task in tasks.items():
            if not task.get("parent"):
                parent_tasks[tid] = task

        # 构建 task 摘要（不含文件内容，仅含文件路径和要求）
        task_summary = ""
        for tid, task in parent_tasks.items():
            task_summary += f"\n### {tid}\n"
            task_summary += f"描述: {task.get('description', '')}\n"
            task_summary += f"文件: {', '.join(task.get('files', []))}\n"
            task_summary += f"要求: {task.get('requirements', '无特殊要求')}\n"
            if task.get("review_feedback"):
                task_summary += f"上次审查反馈: {task['review_feedback']}\n"
            task_summary += "\n"

        # 获取完整 output 框架文本
        framework = output_mgr.get_framework()

        sys_msg = PHASE3_REVIEW_SYSTEM
        if system_prompt:
            sys_msg = f"{system_prompt}\n\n---\n\n{sys_msg}"

        user_msg = PHASE3_REVIEW_USER.format(
            user_message=user_message,
            file_paths=file_paths_text,
            task_summary=task_summary,
            framework=framework,
            principle=output_mgr.get_principle_text(),
            previous_feedback=previous_feedback if previous_feedback else "(首次审查)",
            attempt_number=attempt,
        )

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]

        def _review_stream(type_, content):
            if stream_callback:
                if type_ == "content":
                    stream_callback(f"fold:阶段三审查第{attempt}次", content)
                else:
                    stream_callback(type_, content)

        def _review_think(content):
            if thinking_callback:
                thinking_callback(content)

        review_response = call_api(
            client, model, messages,
            callback=_review_stream,
            thinking_callback=_review_think,
            extra_body=extra_body,
            max_tokens=max_tokens,
            temperature=temperature,
            stop_check=stop_check,
        )

        # ── 解析审查结果 ──
        passed, failed_task_ids, feedback, associated_tasks = _parse_review_result(review_response)

        if passed:
            result.passed = True
            result.final_feedback = "审查通过"
            if progress_callback:
                tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
                progress_callback("阶段三完成：审查通过", tasklist)
            return result

        # ── 审查未通过，需要重做 ──
        result.final_feedback = feedback

        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback(f"阶段三：审查未通过，重做 {failed_task_ids}", tasklist)

        # ── 构建兄弟任务上下文（让每个重做的 task 知道其他失败 task 的信息） ──
        valid_failed = [tid for tid in failed_task_ids if tid in tasks]
        sibling_context = _build_sibling_context(tasks, valid_failed)

        # ── 如果已有 2 次以上尝试且有协调重做器，使用协调模式 ──
        if attempt >= 2 and coordinated_runner and len(valid_failed) > 1:
            if progress_callback:
                tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
                progress_callback(f"阶段三：触发协调重做模式 {valid_failed}", tasklist)

            # 先标记所有失败 task 为 error
            for failed_tid in valid_failed:
                output_mgr.mark_error(failed_tid, feedback)
                result.redone_tasks.append(failed_tid)

            success = coordinated_runner(valid_failed, feedback)
            if success:
                previous_feedback = f"第{attempt}次审查失败后协调重做完成，涉及：{', '.join(valid_failed)}。\n"
            else:
                previous_feedback = f"第{attempt}次审查失败后协调重做未完全成功，涉及：{', '.join(valid_failed)}。\n"
        else:
            # ── 普通模式：逐个重做，但注入兄弟上下文和关联 task 上下文 ──
            # 关键：每重做一个 task 后重建兄弟上下文，让后续重做能看到前一个 task 的修改内容（同审查周期内）
            for idx, failed_tid in enumerate(valid_failed):
                # 标记为 error 并重做
                output_mgr.mark_error(failed_tid, feedback)
                result.redone_tasks.append(failed_tid)

                # 获取该 task 的关联 task 列表
                task_associated = associated_tasks.get(failed_tid, [])

                # 通过 phase2_runner 重做该 task（传入兄弟上下文和关联 task）
                if phase2_runner:
                    success = phase2_runner(
                        failed_tid,
                        sibling_context=sibling_context,
                        associated_tasks=task_associated,
                    )
                    if not success:
                        previous_feedback = f"task {failed_tid} 重做失败。\n" + previous_feedback
                    else:
                        previous_feedback = f"task {failed_tid} 已重做。\n" + previous_feedback
                else:
                    previous_feedback = f"task {failed_tid} 标记重做（无 runner）。\n" + previous_feedback

                # 关键：重做后重建兄弟上下文，让下一个重做看到当前 task 的修改内容（不跨审查周期）
                if idx < len(valid_failed) - 1:
                    latest_tasks = output_mgr.get_all_tasks()
                    sibling_context = _build_sibling_context(latest_tasks, valid_failed)

        previous_feedback = feedback + "\n" + previous_feedback

        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback(f"阶段三：task 重做完成，准备下一次审查", tasklist)

    # ── 达到最大次数 ──
    result.passed = False
    result.final_feedback = f"已达到最大审查次数 ({MAX_REVIEW_ATTEMPTS})，以当前结果作为最终输出。"
    if progress_callback:
        tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
        progress_callback("阶段三：达到最大审查次数", tasklist)
    return result


def _build_sibling_context(tasks: dict, failed_ids: list) -> str:
    """
    为每个重做的 task 构建兄弟任务上下文。
    包含其他失败 task 的描述、文件、要求、当前完整内容，
    让重做时能与兄弟 task 保持一致。
    """
    if len(failed_ids) <= 1:
        return ""

    parts = []
    for tid in failed_ids:
        task = tasks.get(tid, {})
        content = task.get("content", "")
        content_full = content if content else "(尚未填充)"
        parts.append(
            f"### {tid}\n"
            f"描述: {task.get('description', '无')}\n"
            f"文件: {', '.join(task.get('files', []))}\n"
            f"要求: {task.get('requirements', '无')}\n"
            f"当前内容:\n{content_full}"
        )
    return "\n\n".join(parts)


def _parse_review_result(response: str) -> tuple:
    """
    解析审查结果。

    AI 可能输出：
    1. "通过" 或 "PASS" → 通过
    2. JSON 格式指出问题 task：
       {
           "passed": false,
           "failed_tasks": ["task1", "task3"],
           "associated_tasks": {
               "task1": ["task2"],
               "task3": ["task4", "task5"]
           },
           "feedback": "task1: 代码不完整..."
       }

    Returns:
        (passed: bool, failed_task_ids: list, feedback: str, associated_tasks: dict)
    """
    stripped = response.strip()

    # 快速判断通过
    pass_keywords = ["通过", "pass", "没有问题", "没有问题", "审查通过", "合格", "PASS"]
    if any(kw in stripped.lower() for kw in pass_keywords) and not any(
        kw in stripped.lower() for kw in ["不通过", "未通过", "问题", "fail", "failed"]
    ):
        return True, [], "审查通过", {}

    # 尝试 JSON 解析
    json_data = _extract_json(response)
    if json_data and isinstance(json_data, dict):
        passed = json_data.get("passed", False)
        if passed:
            return True, [], "审查通过", {}
        failed = json_data.get("failed_tasks", [])
        if isinstance(failed, list):
            failed = [str(f).lower() for f in failed]
        feedback = json_data.get("feedback", response)
        associated = json_data.get("associated_tasks", {})
        if not isinstance(associated, dict):
            associated = {}
        # 将 associated_tasks 的 key 也转换为小写
        associated = {str(k).lower(): [str(v).lower() for v in vs] if isinstance(vs, list) else []
                      for k, vs in associated.items()}
        if failed:
            return False, failed, feedback, associated

    # 尝试从文本中提取失败 task ID
    failed_pattern = re.findall(r'\[(task[\d_]+)\]', response, re.IGNORECASE)
    if failed_pattern:
        failed = list(set(t.lower() for t in failed_pattern))
        return False, failed, response, {}

    # 无法解析，默认通过（避免无限循环）
    return True, [], "审查结果无法解析，默认通过", {}


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
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None
