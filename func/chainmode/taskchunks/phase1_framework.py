"""
phase1_framework.py - 阶段一：框架构建与任务审查
Part I: 文件读取与校验（可发起 stop 提问）
Part II: 构建输出框架（[task_n] 占位符格式）
Part III: 任务定义审查（最多 3 次循环）
"""
import json
import os
import re
from typing import Optional, Callable

from .api_caller import call_api, get_extra_body
from .file_reader import build_file_map, read_file_full, resolve_file
from .output_manager import OutputManager
from .task_manager import build_tasklist_for_ui
from ..agent_prompts import (
    PHASE1_READ_SYSTEM, PHASE1_READ_USER,
    PHASE1_FRAMEWORK_SYSTEM, PHASE1_FRAMEWORK_USER,
    PHASE1_TASKREVIEW_SYSTEM, PHASE1_TASKREVIEW_USER,
    TASK_SPLITTING_RULES_CODE, TASK_SPLITTING_RULES_ARTICLE, TASK_SPLITTING_RULES_RP,
)


class Phase1Result:
    """阶段一执行结果"""
    def __init__(self):
        self.stopped = False          # True = AI 决定 stop，向用户提问
        self.stop_question = ""       # stop 时的提问文本
        self.framework_text = ""      # Part II 输出的框架文本
        self.file_list_text = ""      # 文件列表文本（供后续审查使用）
        self.tasks = {}               # {task_id: {description, files, requirements, ...}}
        self.output_manager: Optional[OutputManager] = None


def run_phase1(
    client,
    model: str,
    platform: str,
    user_message: str,
    selected_files: list,
    root_path: str,
    history_text: str,
    system_prompt: str,
    temp_dir: str,
    thinking_level: str = "high",
    max_tokens: int = 65536,
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    stop_check: Optional[Callable] = None,
    stop_history: str = "",
    agent_mode: str = "code",
) -> Phase1Result:
    """
    执行阶段一：大框架构建。

    Args:
        ...: 标准 Agent 参数
        temp_dir: records/对话文件夹/temp 路径

    Returns:
        Phase1Result
    """
    result = Phase1Result()
    extra_body = get_extra_body(platform, thinking_level)

    # ── 构建文件映射 ──
    file_list_text, file_map = build_file_map(selected_files, root_path)
    result.file_list_text = file_list_text

    # ── 创建 OutputManager ──
    output_mgr = OutputManager(temp_dir)
    result.output_manager = output_mgr

    # ═══════════════════════════════════════════
    # Part I: 文件读取与 stop 检查
    # ═══════════════════════════════════════════
    if progress_callback:
        progress_callback("阶段一 Part I：读取文件并检查", [])

    # 构造系统消息（含用户自定义 system_prompt）
    sys_msg = PHASE1_READ_SYSTEM
    if system_prompt:
        sys_msg = f"{system_prompt}\n\n---\n\n{sys_msg}"

    # 读取所有选中文件的完整内容（不截断）
    file_preview = ""
    for fpath in selected_files:
        if os.path.isfile(fpath):
            relpath = os.path.relpath(fpath, root_path) if root_path else fpath
            content = read_file_full(fpath)
            file_preview += f"\n### {relpath}\n```\n{content}\n```\n"

    read_messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": PHASE1_READ_USER.format(
            user_message=user_message,
            file_list=file_list_text,
            file_preview=file_preview if file_preview else "(未选择文件)",
            history=history_text,
            stop_history=stop_history if stop_history else "(无 stop 记录)",
        )}
    ]

    def _read_stream(type_, content):
        if stream_callback:
            if type_ == "content":
                stream_callback("fold:阶段一文件检查", content)
            else:
                stream_callback(type_, content)

    def _read_think(content):
        if thinking_callback:
            thinking_callback(content)

    read_response = call_api(
        client, model, read_messages,
        callback=_read_stream,
        thinking_callback=_read_think,
        extra_body=extra_body,
        max_tokens=max_tokens,
        temperature=temperature,
        stop_check=stop_check,
    )

    # 检查是否触发 stop
    stop_match = re.search(r'\[STOP\]\s*(.*?)(?:\[\/STOP\]|$)', read_response, re.DOTALL)
    if stop_match:
        result.stopped = True
        result.stop_question = stop_match.group(1).strip()
        if not result.stop_question:
            result.stop_question = "AI 认为需要更多信息，请补充后重新发送。"
        return result

    # ═══════════════════════════════════════════
    # Part II: 框架构建
    # ═══════════════════════════════════════════
    if progress_callback:
        progress_callback("阶段一 Part II：构建输出框架", [])

    # 读取完整文件内容传给框架阶段（AI 需要看到代码才能决定 task 划分）
    full_file_content = ""
    for fpath in selected_files:
        if os.path.isfile(fpath):
            relpath = os.path.relpath(fpath, root_path) if root_path else fpath
            content = read_file_full(fpath)
            full_file_content += f"\n### 文件: {relpath}\n```\n{content}\n```\n"

    fw_sys_msg = PHASE1_FRAMEWORK_SYSTEM
    if system_prompt:
        fw_sys_msg = f"{system_prompt}\n\n---\n\n{fw_sys_msg}"

    splitting_rules = {
        "code": TASK_SPLITTING_RULES_CODE,
        "article": TASK_SPLITTING_RULES_ARTICLE,
        "rp": TASK_SPLITTING_RULES_RP,
    }.get(agent_mode, TASK_SPLITTING_RULES_CODE)
    fw_sys_msg = fw_sys_msg.replace("{task_splitting_rules}", splitting_rules)

    fw_messages = [
        {"role": "system", "content": fw_sys_msg},
        {"role": "user", "content": PHASE1_FRAMEWORK_USER.format(
            user_message=user_message,
            file_list=file_list_text,
            file_contents=full_file_content if full_file_content else "(未选择文件)",
            history=history_text,
        )}
    ]

    def _fw_stream(type_, content):
        if stream_callback:
            if type_ == "content":
                stream_callback("fold:阶段一框架构建", content)
            else:
                stream_callback(type_, content)

    def _fw_think(content):
        if thinking_callback:
            thinking_callback(content)

    framework_response = call_api(
        client, model, fw_messages,
        callback=_fw_stream,
        thinking_callback=_fw_think,
        extra_body=extra_body,
        max_tokens=max_tokens,
        temperature=temperature,
        stop_check=stop_check,
    )

    # ── 解析框架输出 ──
    framework_text, tasks = _parse_framework_output(framework_response)

    result.framework_text = framework_text
    result.tasks = tasks

    # ── 保存到 output.json ──
    output_mgr.initialize(framework=framework_text, tasks=tasks)

    # ── 更新 UI tasklist ──
    if progress_callback:
        tasklist = build_tasklist_for_ui(tasks)
        progress_callback("阶段一完成：框架构建完毕", tasklist)

    return result


def _parse_framework_output(response: str) -> tuple:
    """
    解析阶段一的框架输出。

    AI 应该输出 JSON 格式：
    {
        "framework": "完整框架文本，含 [task1] [task2] 占位符",
        "tasks": {
            "task1": {
                "description": "详细描述",
                "files": ["文件路径"],
                "requirements": "任务要求提示词"
            },
            ...
        }
    }

    兼容纯文本框架（fallback）。
    """
    tasks = {}
    framework_text = response

    # 尝试 JSON 解析
    json_data = _extract_json(response)
    if json_data and "framework" in json_data and "tasks" in json_data:
        framework_text = json_data["framework"]
        # 剥离 AI 可能在 framework 字段值中添加的外层代码围栏
        # 例如 AI 输出 framework: "```python\n...\n```" 时需要去掉外层围栏
        framework_text = _strip_outer_fence(framework_text)
        for tid, tdata in json_data["tasks"].items():
            tasks[tid] = {
                "status": "pending",
                "description": tdata.get("description", ""),
                "files": tdata.get("files", []),
                "requirements": tdata.get("requirements", ""),
                "preset": tdata.get("preset", "mixed"),
                "content": "",
                "retry_count": 0,
                "review_feedback": "",
            }
        return framework_text, tasks

    # Fallback: 从文本中提取 [task_n] 占位符，自动生成 task 条目
    task_pattern = re.findall(r'\[(task[\d_]+)\]', response, re.IGNORECASE)
    seen = set()
    for i, tid in enumerate(task_pattern, 1):
        tid_lower = tid.lower()
        if tid_lower not in seen:
            seen.add(tid_lower)
            tasks[tid_lower] = {
                "status": "pending",
                "description": f"任务 {tid_lower}（需根据上下文填充）",
                "files": [],
                "requirements": "",
                "preset": "mixed",
                "content": "",
                "retry_count": 0,
                "review_feedback": "",
            }

    return framework_text, tasks


def _strip_outer_fence(text: str) -> str:
    """
    剥离文本最外层的代码围栏。
    AI 有时会在 framework 字段值中添加外层围栏，如：
    ```python\n...\n``` 或 ```\n...\n```
    需要去掉这层围栏，保留内部内容。
    """
    stripped = text.strip()
    if not stripped.startswith('```'):
        return text

    lines = stripped.split('\n')
    if len(lines) < 2:
        return text

    # 查找与首行 ``` 对应的闭合 ```
    # 首行可能是 ``` 或 ```language
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() == '```':
            # 检查这是否是首行的配对（中间不应有未配对的 ```）
            inner_text = '\n'.join(lines[1:i])
            # 验证内部围栏是配对的
            fence_count = inner_text.count('```')
            if fence_count % 2 == 0:
                return inner_text
            break

    return text


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


def run_task_review(
    client,
    model: str,
    platform: str,
    user_message: str,
    file_list_text: str,
    history_text: str,
    system_prompt: str,
    output_mgr: OutputManager,
    extra_body: dict,
    max_tokens: int = 65536,
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    stop_check: Optional[Callable] = None,
    agent_mode: str = "code",
) -> None:
    """
    Part III: 审查 task 定义合理性，最多循环 3 次。
    审查通过后直接更新 output_mgr 中的 tasks。
    """
    max_review_rounds = 3
    previous_feedback = "(首次审查)"

    for round_num in range(1, max_review_rounds + 1):
        if progress_callback:
            from .task_manager import build_tasklist_for_ui
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback(f"阶段一 Part III：审查任务定义（第 {round_num}/{max_review_rounds} 轮）", tasklist)

        # 构建任务列表文本
        tasks = output_mgr.get_all_tasks()
        task_list_text = ""
        for tid, task in tasks.items():
            task_list_text += f"\n### {tid}\n"
            task_list_text += f"描述: {task.get('description', '')}\n"
            task_list_text += f"文件: {', '.join(task.get('files', []))}\n"
            task_list_text += f"要求: {task.get('requirements', '')}\n"
            task_list_text += f"预设: {task.get('preset', 'mixed')}\n"

        sys_msg = PHASE1_TASKREVIEW_SYSTEM
        if system_prompt:
            sys_msg = f"{system_prompt}\n\n---\n\n{sys_msg}"

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": PHASE1_TASKREVIEW_USER.format(
                user_message=user_message,
                file_list=file_list_text,
                task_list=task_list_text,
                history=history_text,
                previous_feedback=previous_feedback,
            )}
        ]

        def _review_stream(type_, content):
            if stream_callback:
                if type_ == "content":
                    stream_callback("fold:阶段一：任务审查", content)
                else:
                    stream_callback(type_, content)

        response = call_api(
            client, model, messages,
            callback=_review_stream,
            thinking_callback=thinking_callback,
            extra_body=extra_body,
            max_tokens=max_tokens,
            temperature=temperature,
            stop_check=stop_check,
        )

        # 解析审查结果
        review_data = None
        response_stripped = response.strip()

        if response_stripped == "PASS" or response_stripped.startswith("PASS"):
            break  # 审查通过

        # 尝试解析 JSON
        try:
            data = json.loads(response_stripped)
            if isinstance(data, dict) and not data.get("passed", True):
                review_data = data
        except (json.JSONDecodeError, ValueError):
            pass

        if review_data is None:
            # 尝试从 markdown 代码块提取
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1).strip())
                    if isinstance(data, dict) and not data.get("passed", True):
                        review_data = data
                except (json.JSONDecodeError, ValueError):
                    pass

        if review_data is None:
            # 无法解析，视为通过
            break

        # 更新 task 定义
        corrected = review_data.get("corrected_tasks", {})
        if corrected:
            current_tasks = output_mgr.get_all_tasks()

            # 同步框架文本（审查者可能拆分/合并了 task）
            corrected_framework = review_data.get("corrected_framework", "")
            if corrected_framework:
                corrected_framework = _strip_outer_fence(corrected_framework)
                output_mgr.set_framework(corrected_framework)

            new_task_ids = set(corrected.keys())
            current_task_ids = set(current_tasks.keys())

            # 更新/新增所有修正后的 task
            for tid, new_def in corrected.items():
                output_mgr.update_task(
                    tid,
                    description=new_def.get("description", current_tasks.get(tid, {}).get("description", "")),
                    files=new_def.get("files", current_tasks.get(tid, {}).get("files", [])),
                    requirements=new_def.get("requirements", current_tasks.get(tid, {}).get("requirements", "")),
                    preset=new_def.get("preset", current_tasks.get(tid, {}).get("preset", "mixed")),
                )

            # 删除不在修正列表中的旧 task（被拆分的旧 task）
            for old_tid in current_task_ids - new_task_ids:
                data = output_mgr.load()
                if old_tid in data["tasks"]:
                    del data["tasks"][old_tid]
                    output_mgr.save()

            previous_feedback = review_data.get("feedback", "")
        else:
            # 没有 corrected_tasks，视为通过
            break

    else:
        # 达到最大轮次，记录最后反馈
        pass

    if progress_callback:
        from .task_manager import build_tasklist_for_ui
        tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
        progress_callback("阶段一 Part III 完成：任务定义已确认", tasklist)


def run_framework_review(
    client,
    model: str,
    platform: str,
    user_message: str,
    selected_files: list,
    root_path: str,
    history_text: str,
    system_prompt: str,
    output_mgr: OutputManager,
    extra_body: dict,
    max_tokens: int = 65536,
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    stop_check: Optional[Callable] = None,
    agent_mode: str = "code",
) -> bool:
    """
    框架审查重建：重新运行框架构建（Part II）和任务审查（Part III）。
    当阶段三审查认为框架本身不合理时调用。

    Returns:
        bool: True 表示重建成功
    """
    if progress_callback:
        progress_callback("阶段三：重建框架", [])

    # 重新读取文件内容
    full_file_content = ""
    file_list_text = ""
    for fpath in selected_files:
        if os.path.isfile(fpath):
            relpath = os.path.relpath(fpath, root_path) if root_path else fpath
            content = read_file_full(fpath)
            full_file_content += f"\n### 文件: {relpath}\n```\n{content}\n```\n"
            file_list_text += f"- {relpath}\n"
    if not file_list_text:
        file_list_text = "(未选择文件)"

    # 重新构建框架（与 Part II 相同逻辑）
    fw_sys_msg = PHASE1_FRAMEWORK_SYSTEM
    if system_prompt:
        fw_sys_msg = f"{system_prompt}\n\n---\n\n{fw_sys_msg}"

    splitting_rules = {
        "code": TASK_SPLITTING_RULES_CODE,
        "article": TASK_SPLITTING_RULES_ARTICLE,
        "rp": TASK_SPLITTING_RULES_RP,
    }.get(agent_mode, TASK_SPLITTING_RULES_CODE)
    fw_sys_msg = fw_sys_msg.replace("{task_splitting_rules}", splitting_rules)

    fw_messages = [
        {"role": "system", "content": fw_sys_msg},
        {"role": "user", "content": PHASE1_FRAMEWORK_USER.format(
            user_message=user_message,
            file_list=file_list_text,
            file_contents=full_file_content if full_file_content else "(未选择文件)",
            history=history_text,
        )}
    ]

    def _fw_stream(type_, content):
        if stream_callback:
            if type_ == "content":
                stream_callback("fold:阶段三框架重建", content)
            else:
                stream_callback(type_, content)

    def _fw_think(content):
        if thinking_callback:
            thinking_callback(content)

    framework_response = call_api(
        client, model, fw_messages,
        callback=_fw_stream,
        thinking_callback=_fw_think,
        extra_body=extra_body,
        max_tokens=max_tokens,
        temperature=temperature,
        stop_check=stop_check,
    )

    # 解析新框架
    framework_text, tasks = _parse_framework_output(framework_response)

    # 更新 output_mgr 中的框架和 tasks
    output_mgr.set_framework(framework_text)
    current_tasks = output_mgr.get_all_tasks()
    for tid, task_data in tasks.items():
        if tid in current_tasks:
            # 保留已有 task 的已有字段，更新描述/文件/要求
            output_mgr.update_task(
                tid,
                description=task_data.get("description", current_tasks[tid].get("description", "")),
                files=task_data.get("files", current_tasks[tid].get("files", [])),
                requirements=task_data.get("requirements", current_tasks[tid].get("requirements", "")),
                preset=task_data.get("preset", current_tasks[tid].get("preset", "mixed")),
            )
        else:
            # 新 task
            output_mgr.update_task(tid, **task_data)

    if progress_callback:
        tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
        progress_callback("阶段三：框架已重建，进行任务审查", tasklist)

    # 重新运行任务审查
    run_task_review(
        client=client,
        model=model,
        platform=platform,
        user_message=user_message,
        file_list_text=file_list_text,
        history_text=history_text,
        system_prompt=system_prompt,
        output_mgr=output_mgr,
        extra_body=extra_body,
        max_tokens=max_tokens,
        temperature=temperature,
        stream_callback=stream_callback,
        thinking_callback=thinking_callback,
        progress_callback=progress_callback,
        stop_check=stop_check,
        agent_mode=agent_mode,
    )

    if progress_callback:
        tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
        progress_callback("阶段三：框架重建完成", tasklist)

    return True
