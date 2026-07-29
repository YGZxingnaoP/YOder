"""
agent_core.py - Agent 模式四阶段编排器
阶段一: 框架构建（Part I 文件读取 + Part II 框架搭建 + Part III 任务审查）
阶段二: 逐 task 内容填充
阶段三: 完整格式和内容审查（最多 6 次）
阶段四: 最终输出
"""
import json
import os
import re
from typing import Optional, Callable

from .taskchunks.api_caller import call_api, get_extra_body, UserStoppedError, ContentFilterError
from .taskchunks.file_reader import build_file_map
from .taskchunks.history_builder import build_history_text, build_brief_history
from .taskchunks.output_manager import OutputManager
from .taskchunks.task_manager import build_tasklist_for_ui
from .taskchunks.phase1_framework import run_phase1, run_task_review, run_framework_review
from .taskchunks.phase2_filler import run_phase2
from .taskchunks.phase3_review import run_phase3
from .agent_prompts import PRINCIPLE_CODE_SYSTEM, PRINCIPLE_GENERAL_SYSTEM, PRINCIPLE_USER


def run_agent_pipeline(
    client,
    model: str,
    platform: str,
    user_message: str,
    selected_files: list,
    root_path: str = "",
    thinking_level: str = "high",
    progress_callback: Optional[Callable] = None,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    history: list = None,
    max_tokens: int = 65536,
    temperature: float = 0.7,
    system_prompt: str = "",
    conversation_folder: str = "",
    stop_callback: Optional[Callable] = None,
    agent_mode: str = "",
    user_stop_check: Optional[Callable] = None,
):
    """
    执行 Agent 四阶段管线。

    回调协议:
    - progress_callback(status: str, tasklist: list)
    - stream_callback(type: str, content: str)
        type = "content"     → 最终输出内容
        type = "fold:名称"   → 折叠块内容（如 "fold:task1思考内容"）
    - thinking_callback(content: str)
        思考内容，UI 会自动包装到命名折叠块中
    - stop_callback(question: str)
        AI 决定停止并向用户提问
    - agent_mode: "code" | "rp" | "article" | ""
        编写准则生成模式，空字符串默认 article
    """
    history = history or []

    # ── 构建对话历史文本 ──
    history_text = build_brief_history(history)

    # ── 准备 temp 目录 ──
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    records_dir = os.path.join(base_dir, "records")
    if conversation_folder:
        temp_dir = os.path.join(records_dir, conversation_folder, "temp")
    else:
        temp_dir = os.path.join(records_dir, "temp")

    # ═══════════════════════════════════════════
    # 阶段一：大框架构建
    # ═══════════════════════════════════════════

    # ── 命名思考回调包装器 ──
    def _named_think(name):
        """创建带名称的思考回调，通过 fold 块输出"""
        def _cb(content):
            if stream_callback:
                stream_callback(f"fold:{name}", content)
        return _cb

    try:
        phase1_result = run_phase1(
            client=client,
            model=model,
            platform=platform,
            user_message=user_message,
            selected_files=selected_files,
            root_path=root_path,
            history_text=history_text,
            system_prompt=system_prompt,
            temp_dir=temp_dir,
            thinking_level=thinking_level,
            max_tokens=max_tokens,
            temperature=temperature,
            stream_callback=stream_callback,
            thinking_callback=_named_think("阶段一思考：文件检查与框架构建"),
            progress_callback=progress_callback,
            stop_check=user_stop_check,
        )
    except ContentFilterError as e:
        # 阶段一就触发了内容安全审查
        if stream_callback:
            stream_callback("content", f"> ⚠️ **API 内容安全审查拒绝**：{e.message}\n> 请检查输入内容后重试。")
        if progress_callback:
            progress_callback("内容安全审查拒绝", [])
        return

    # ── 检查 stop ──
    if phase1_result.stopped:
        if stop_callback:
            stop_callback(phase1_result.stop_question)
        return

    output_mgr = phase1_result.output_manager

    # ═══════════════════════════════════════════
    # 剩余阶段包裹在 try/except 中，用户停止时输出已完成的任务内容
    # ═══════════════════════════════════════════
    try:

        # ═══════════════════════════════════════════
        # 阶段一 Part III：任务定义审查
        # ═══════════════════════════════════════════

        run_task_review(
            client=client,
            model=model,
            platform=platform,
            user_message=user_message,
            file_list_text=phase1_result.file_list_text,
            history_text=history_text,
            system_prompt=system_prompt,
            output_mgr=output_mgr,
            extra_body=get_extra_body(platform, thinking_level),
            max_tokens=max_tokens,
            temperature=temperature,
            stream_callback=stream_callback,
            thinking_callback=_named_think("阶段一思考：任务审查"),
            progress_callback=progress_callback,
            stop_check=user_stop_check,
        )

        # ═══════════════════════════════════════════
        # 阶段一 Part IV：编写准则生成
        # ═══════════════════════════════════════════

        effective_mode = agent_mode if agent_mode else "code"

        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback(f"阶段一：生成编写准则（{effective_mode}模式）", tasklist)

        _generate_principle(
            client=client,
            model=model,
            platform=platform,
            user_message=user_message,
            output_mgr=output_mgr,
            thinking_level=thinking_level,
            temperature=temperature,
            stream_callback=stream_callback,
            thinking_callback=_named_think("阶段一思考：编写准则"),
            agent_mode=effective_mode,
            system_prompt=system_prompt,
            stop_check=user_stop_check,
        )

        # ═══════════════════════════════════════════
        # 阶段二：逐 task 内容填充
        # ═══════════════════════════════════════════

        def _run_phase2_for_tasks():
            """执行阶段二填充"""
            return run_phase2(
                client=client,
                model=model,
                platform=platform,
                user_message=user_message,
                selected_files=selected_files,
                root_path=root_path,
                history_text=history_text,
                system_prompt=system_prompt,
                output_mgr=output_mgr,
                thinking_level=thinking_level,
                max_tokens=max_tokens,
                temperature=temperature,
                stream_callback=stream_callback,
                thinking_callback=_named_think("阶段二思考：任务填充"),
                progress_callback=progress_callback,
                stop_check=user_stop_check,
            )

        phase2_result = _run_phase2_for_tasks()

        # ═══════════════════════════════════════════
        # 阶段三：完整格式和内容审查
        # ═══════════════════════════════════════════

        def _redo_single_task(task_id: str, sibling_context: str = "", associated_tasks: list = None) -> bool:
            """
            重做单个 task（阶段三审查不通过时调用）。
            通过直接运行 phase2 对该 task 进行重填充。
            保留 review_feedback + sibling_context + associated_tasks 内容，
            让 AI 知道上次哪里出了问题、兄弟 task 的情况，以及关联 task 的完整内容。
            """
            # 先恢复框架中的占位符，否则新内容无法写入框架
            output_mgr.restore_task_placeholder(task_id)

            # 获取当前 review_feedback（由 mark_error 设置），增强后保留
            current_feedback = ""
            task_data = output_mgr.get_task(task_id)
            if task_data:
                current_feedback = task_data.get("review_feedback", "")

            # 构建关联 task 上下文（用于重做时参考）
            associated_context = ""
            associated_parts = []
            if associated_tasks:
                all_tasks = output_mgr.get_all_tasks()
                for assoc_tid in associated_tasks:
                    assoc_task = all_tasks.get(assoc_tid, {})
                    if assoc_task:
                        assoc_content = assoc_task.get("content", "")
                        if not assoc_content:
                            assoc_content = "(尚未填充)"
                        associated_parts.append(
                            f"### {assoc_tid}\n"
                            f"描述: {assoc_task.get('description', '无')}\n"
                            f"文件: {', '.join(assoc_task.get('files', []))}\n"
                            f"要求: {assoc_task.get('requirements', '无')}\n"
                            f"当前内容:\n{assoc_content}"
                        )
            if associated_parts:
                associated_context = "\n\n".join(associated_parts)

            # 将 task 状态重置为 pending，但增强 review_feedback
            enhanced_feedback = current_feedback
            if sibling_context:
                enhanced_feedback = (
                    f"{enhanced_feedback}\n\n"
                    f"## 同时被重做的兄弟任务信息（请务必与它们保持一致）：\n{sibling_context}"
                )
            if associated_context:
                enhanced_feedback = (
                    f"{enhanced_feedback}\n\n"
                    f"## 关联任务内容（重做时请务必参考这些任务的内容，确保接口和逻辑一致）：\n{associated_context}"
                )
            output_mgr.update_task(task_id, status="pending", content="", review_feedback=enhanced_feedback)

            # 重新运行 phase2（它会自动找到 pending 的 task 并填充）
            redo_result = run_phase2(
                client=client,
                model=model,
                platform=platform,
                user_message=user_message,
                selected_files=selected_files,
                root_path=root_path,
                history_text=history_text,
                system_prompt=system_prompt,
                output_mgr=output_mgr,
                thinking_level=thinking_level,
                max_tokens=max_tokens,
                temperature=temperature,
                stream_callback=stream_callback,
                thinking_callback=_named_think(f"重做{task_id}思考内容"),
                progress_callback=progress_callback,
                stop_check=user_stop_check,
            )
            return task_id not in redo_result.failed_tasks

        def _coordinated_redo_all(failed_task_ids: list, feedback: str) -> bool:
            """
            协调重做：将多个失败 task 一起重置并一起填充，
            使 AI 在一次调用中看到所有失败 task 的信息，避免交叉不一致。
            """
            # 构建兄弟任务上下文
            all_tasks = output_mgr.get_all_tasks()
            sibling_parts = []
            for tid in failed_task_ids:
                t = all_tasks.get(tid, {})
                sibling_parts.append(
                    f"- {tid}: 描述={t.get('description', '无')}\n"
                    f"  文件={', '.join(t.get('files', []))}\n"
                    f"  要求={t.get('requirements', '无')}"
                )
            sibling_ctx = "\n".join(sibling_parts)

            coord_feedback = (
                f"{feedback}\n\n"
                f"## 协调重做指令\n"
                f"以下任务因交叉不一致被反复打回，本次将一起重做。\n"
                f"请务必确保所有任务之间的接口（函数名、字典键名、文件路径、命名规则等）完全一致。\n\n"
                f"## 需要协调的任务列表：\n{sibling_ctx}"
            )

            # 恢复所有失败 task 的占位符并重置状态
            for tid in failed_task_ids:
                output_mgr.restore_task_placeholder(tid)
                output_mgr.update_task(tid, status="pending", content="", review_feedback=coord_feedback)

            # 一次 phase2 调用处理所有 pending task
            redo_result = run_phase2(
                client=client,
                model=model,
                platform=platform,
                user_message=user_message,
                selected_files=selected_files,
                root_path=root_path,
                history_text=history_text,
                system_prompt=system_prompt,
                output_mgr=output_mgr,
                thinking_level=thinking_level,
                max_tokens=max_tokens,
                temperature=temperature,
                stream_callback=stream_callback,
                thinking_callback=_named_think("协调重做思考内容"),
                progress_callback=progress_callback,
                stop_check=user_stop_check,
            )
            return len(redo_result.failed_tasks) == 0

        def _redo_framework() -> bool:
            """
            重建整个框架（阶段三审查发现框架本身不合理时调用）。
            重新运行框架构建 + 任务审查，然后重新执行所有 task 的填充。
            """
            return run_framework_review(
                client=client,
                model=model,
                platform=platform,
                user_message=user_message,
                selected_files=selected_files,
                root_path=root_path,
                history_text=history_text,
                system_prompt=system_prompt,
                output_mgr=output_mgr,
                extra_body=get_extra_body(platform, thinking_level),
                max_tokens=max_tokens,
                temperature=temperature,
                stream_callback=stream_callback,
                thinking_callback=_named_think("阶段三思考：框架重建"),
                progress_callback=progress_callback,
                stop_check=user_stop_check,
            )

        phase3_result = run_phase3(
            client=client,
            model=model,
            platform=platform,
            user_message=user_message,
            selected_files=selected_files,
            root_path=root_path,
            system_prompt=system_prompt,
            output_mgr=output_mgr,
            thinking_level=thinking_level,
            max_tokens=max_tokens,
            temperature=temperature,
            stream_callback=stream_callback,
            thinking_callback=_named_think("阶段三思考：审查"),
            progress_callback=progress_callback,
            phase2_runner=_redo_single_task,
            coordinated_runner=_coordinated_redo_all,
            framework_runner=_redo_framework,
            stop_check=user_stop_check,
        )

        # ═══════════════════════════════════════════
        # 阶段四：最终输出
        # ═══════════════════════════════════════════
        if progress_callback:
            tasklist = build_tasklist_for_ui(output_mgr.get_all_tasks())
            progress_callback("阶段四：生成最终输出", tasklist)

        final_output = output_mgr.get_final_output()

        # 流式输出最终内容
        if stream_callback and final_output:
            chunk_size = 50
            for i in range(0, len(final_output), chunk_size):
                chunk = final_output[i:i + chunk_size]
                stream_callback("content", chunk)

        if progress_callback:
            progress_callback("全部完成", [])

    except UserStoppedError:
        # ═══════════════════════════════════════════
        # 用户停止：保留并输出已完成的任务内容
        # ═══════════════════════════════════════════
        if output_mgr:
            final_output = output_mgr.get_final_output()
            if final_output:
                # 清理未填充的 task 占位符（未完成的 task）
                tasks = output_mgr.get_all_tasks()
                for tid, task in tasks.items():
                    if not task.get("content"):
                        placeholder = f"[{tid}]"
                        final_output = final_output.replace(placeholder, "")
                # 清理多余空行
                final_output = re.sub(r'\n{3,}', '\n\n', final_output).strip()

                if final_output:
                    # 添加停止提示
                    final_output += "\n\n---\n> ⏹ **用户停止了生成**（已完成的任务内容已保留）"
                    # 流式输出已完成的内容
                    if stream_callback:
                        chunk_size = 50
                        for i in range(0, len(final_output), chunk_size):
                            chunk = final_output[i:i + chunk_size]
                            stream_callback("content", chunk)

        if progress_callback:
            progress_callback("用户已停止", [])

    except ContentFilterError as e:
        # ═══════════════════════════════════════════
        # 内容安全审查拒绝：输出已完成内容 + 错误提示
        # ═══════════════════════════════════════════
        if output_mgr:
            final_output = output_mgr.get_final_output()
            if final_output:
                tasks = output_mgr.get_all_tasks()
                for tid, task in tasks.items():
                    if not task.get("content"):
                        placeholder = f"[{tid}]"
                        final_output = final_output.replace(placeholder, "")
                final_output = re.sub(r'\n{3,}', '\n\n', final_output).strip()

                if final_output:
                    final_output += f"\n\n---\n> ⚠️ **API 内容安全审查拒绝**：{e.message}\n> 已完成的任务内容已保留，请检查输入内容后重试。"
                    if stream_callback:
                        chunk_size = 50
                        for i in range(0, len(final_output), chunk_size):
                            chunk = final_output[i:i + chunk_size]
                            stream_callback("content", chunk)
        else:
            # 阶段一就触发了，没有 output_mgr，直接流式输出错误信息
            if stream_callback:
                error_msg = f"> ⚠️ **API 内容安全审查拒绝**：{e.message}\n> 请检查输入内容后重试。"
                stream_callback("content", error_msg)

        if progress_callback:
            progress_callback("内容安全审查拒绝", [])


def _generate_principle(
    client,
    model: str,
    platform: str,
    user_message: str,
    output_mgr: OutputManager,
    thinking_level: str = "high",
    temperature: float = 0.7,
    stream_callback: Optional[Callable] = None,
    thinking_callback: Optional[Callable] = None,
    agent_mode: str = "code",
    system_prompt: str = "",
    stop_check: Optional[Callable] = None,
):
    """
    在阶段一完成后生成编写准则（principle.json）。
    根据 agent_mode 选择不同的提示词模板。
    max_tokens 硬编码为 8192，防止输出过多。
    """
    extra_body = get_extra_body(platform, thinking_level)

    # 构建任务列表摘要
    tasks = output_mgr.get_all_tasks()
    task_list_text = ""
    for tid, task in tasks.items():
        if not task.get("parent"):
            task_list_text += f"\n### {tid}\n"
            task_list_text += f"描述: {task.get('description', '')}\n"
            task_list_text += f"文件: {', '.join(task.get('files', []))}\n"
            task_list_text += f"要求: {task.get('requirements', '')}\n"

    # 选择系统提示词
    if agent_mode == "code":
        sys_msg = PRINCIPLE_CODE_SYSTEM
    else:
        sys_msg = PRINCIPLE_GENERAL_SYSTEM

    if system_prompt:
        sys_msg = f"{system_prompt}\n\n---\n\n{sys_msg}"

    user_msg = PRINCIPLE_USER.format(
        user_message=user_message,
        framework=output_mgr.get_framework(),
        task_list=task_list_text,
    )

    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_msg},
    ]

    def _principle_stream(type_, content):
        if stream_callback:
            if type_ == "content":
                stream_callback("fold:编写准则生成", content)
            else:
                stream_callback(type_, content)

    response = call_api(
        client, model, messages,
        callback=_principle_stream,
        thinking_callback=thinking_callback,
        extra_body=extra_body,
        max_tokens=16384,  # 准则需要详细输出，提高上限
        temperature=temperature,
        stop_check=stop_check,
    )

    # 解析输出并保存
    principle = _extract_principle_json(response)
    output_mgr.set_principle(principle)


def _extract_principle_json(text: str) -> dict:
    """从 AI 输出中提取准则 JSON"""
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return data
    except:
        pass
    # 尝试从 markdown 代码块提取
    import re
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                return data
        except:
            pass
    # 最后尝试查找任意 JSON 对象
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except:
            pass
    return {}
