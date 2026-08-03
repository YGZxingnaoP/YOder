"""
对话核心路由（/api/chat、/api/chat/stop）
包含标准模式（GoalExecutor）和旧版思维链模式（chainmode）
"""
import asyncio
import json
import os
import uuid
import platform as _platform

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from func.api import config
from func.api.config import BASE_DIR, _stop_flags, get_config_dict
from func.api.models import ChatRequest
from func.chatbot.tools_port_factory import ToolsPortFactory, PLATFORM_BASE_URLS
from func.agent.goal_executor import GoalExecutor

router = APIRouter()


# ──────────────────────────────────────────────
# 旧版思维链模式（chainmode）桥接器
# ──────────────────────────────────────────────

async def _run_legacy_chain(
    client, model, platform, user_message, selected_files,
    root_path, thinking_level, history, max_tokens, temperature,
    system_prompt, conversation_folder, agent_mode, should_stop,
):
    """
    旧版思维链模式：在后台线程运行 chainmode 四阶段管线，
    通过 asyncio.Queue 桥接到 async generator，输出前端兼容的协议标记。

    协议标记：
    - \\x01 + text: thinking/折叠块内容
    - \\x02 + text: 正文内容
    """
    from func.chainmode.agent_core import run_agent_pipeline
    from func.chainmode.taskchunks.api_caller import UserStoppedError, ContentFilterError

    queue = asyncio.Queue()
    accumulated_content = []  # 收集最终输出内容

    def stream_cb(type_, content):
        """chainmode 流式回调 → queue"""
        if type_ == "content":
            queue.put_nowait(("content", content))
        elif type_.startswith("fold:"):
            # 折叠块 → 作为 thinking 输出
            queue.put_nowait(("fold", content))

    def progress_cb(status, tasklist):
        """chainmode 进度回调 → queue"""
        queue.put_nowait(("progress", status))

    def stop_cb(question):
        """chainmode AI 叫停回调 → queue"""
        queue.put_nowait(("stop", question))

    def run_in_thread():
        """在后台线程运行同步的 chainmode 管线"""
        try:
            run_agent_pipeline(
                client=client,
                model=model,
                platform=platform,
                user_message=user_message,
                selected_files=selected_files,
                root_path=root_path,
                thinking_level=thinking_level,
                progress_callback=progress_cb,
                stream_callback=stream_cb,
                thinking_callback=None,
                history=history,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
                conversation_folder=conversation_folder,
                stop_callback=stop_cb,
                agent_mode=agent_mode,
                user_stop_check=should_stop,
            )
        except (UserStoppedError, Exception) as e:
            queue.put_nowait(("error", str(e)))
        finally:
            queue.put_nowait(None)  # 哨兵值，表示完成

    # 启动后台线程
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_in_thread)

    # 从 queue 消费并 yield 前端兼容的协议标记
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            # 检查停止标志
            if should_stop():
                yield "\x02\n\n> ⏹ **用户停止了生成**"
                break
            continue

        if item is None:
            break  # 完成

        type_, data = item

        if type_ == "content":
            accumulated_content.append(data)
            yield "\x02" + data
        elif type_ == "fold":
            yield "\x01" + data
        elif type_ == "progress":
            # 进度信息作为 thinking 输出
            yield "\x01" + f"> 📋 {data}\n"
        elif type_ == "stop":
            yield "\x02" + f"\n> ❓ **AI 叫停并提问**: {data}"
            break
        elif type_ == "error":
            if not should_stop():
                yield "\x02" + f"\n> ⚠️ 错误: {data}"
            break

    # 清空 queue 中可能剩余的项
    while not queue.empty():
        try:
            remaining = queue.get_nowait()
            if remaining is not None:
                type_, data = remaining
                if type_ == "content":
                    yield "\x02" + data
        except asyncio.QueueEmpty:
            break


# ──────────────────────────────────────────────
# /api/chat/stop
# ──────────────────────────────────────────────

@router.post("/api/chat/stop")
async def stop_chat(chat_id: str):
    """停止指定对话的AI输出"""
    _stop_flags[chat_id] = True
    return {"status": "success"}


# ──────────────────────────────────────────────
# /api/chat（核心对话端点）
# ──────────────────────────────────────────────

@router.post("/api/chat")
async def chat(request: ChatRequest):
    """发送消息并获取AI响应(支持Tool Calls)"""

    async def generate():
        try:
            # 清除停止标志
            _stop_flags.pop(request.chat_id, None)

            # 1. 加载全局配置
            cfg = get_config_dict()
            platform = cfg.get("platform", "阿里")
            model = cfg.get("model", "qwen-max")
            max_tokens = cfg.get("max_tokens", 65536)
            temperature = cfg.get("temperature", 0.7)
            thinking_level = cfg.get("thinking_level", "high")
            agent_mode = request.agent_mode or ""

            # 1.5 检查对话级配置覆盖
            chat_config_path = os.path.join(BASE_DIR, "records", request.chat_id, "model.json")
            if os.path.exists(chat_config_path):
                try:
                    with open(chat_config_path, "r", encoding="utf-8") as f:
                        chat_config = json.load(f)
                    if chat_config.get("platform"):
                        platform = chat_config["platform"]
                    if chat_config.get("model"):
                        model = chat_config["model"]
                    if chat_config.get("max_tokens"):
                        max_tokens = chat_config["max_tokens"]
                    if chat_config.get("temperature") is not None:
                        temperature = chat_config["temperature"]
                    if chat_config.get("thinking_level"):
                        thinking_level = chat_config["thinking_level"]
                    if chat_config.get("agent_mode"):
                        agent_mode = chat_config["agent_mode"]
                except Exception:
                    pass

            # 2. 创建ToolsPort
            api_keys = cfg.get("api_keys", {})
            api_key = api_keys.get(platform, "")

            if not api_key:
                yield f"[错误] {platform} API Key未配置"
                return

            tools_port = ToolsPortFactory.create(platform=platform, api_key=api_key)

            # 2.5 构建系统提示词（项目路径+OS+加载文件夹）
            os_info = f"{_platform.system()} {_platform.release()} ({_platform.machine()})"
            project_root = BASE_DIR
            loaded_folder = request.loaded_folder or ""

            system_prompt_parts = [
                f"你是一个AI编程助手，运行在 {os_info} 系统上。",
                f"项目根目录为: {project_root}",
            ]
            if loaded_folder:
                system_prompt_parts.append(f"\n[当前工作目录]")
                system_prompt_parts.append(f"用户已加载工作文件夹: {loaded_folder}")
                system_prompt_parts.append(f"bash工具的默认工作目录已设为该文件夹，执行命令时无需指定working_dir，命令将自动在该目录下执行。")
                system_prompt_parts.append(f"请使用该文件夹内的相对路径来引用文件，工具调用时优先使用相对于 {loaded_folder} 的路径。")
            else:
                system_prompt_parts.append(f"\n[当前工作目录]")
                system_prompt_parts.append(f"bash工具的默认工作目录为 D:\\，执行命令时将自动在该目录下执行。")
            system_prompt_parts.append("当使用工具操作文件时，请使用绝对路径或相对于工作目录的路径。")
            system_prompt_parts.append("\n[bash工具环境说明]")
            system_prompt_parts.append("bash工具在Windows下使用 cmd.exe 执行命令，请使用cmd语法（如 dir /b /ad、type、findstr 等），不要使用PowerShell语法（如 Get-ChildItem、Select-Object 等）。")

            # ═══ 工具使用引导 ═══
            if request.tools_enabled:
                tool_guidance = (
                    "\n\n[工具使用指南]\n"
                    "你拥有以下工具，请高效使用:\n"
                    "- todolist: 任务规划工具。对于复杂任务(如分析项目、多步开发)，你必须先用todolist创建任务计划，然后逐步执行并更新状态。当所有任务完成时，循环将自动结束。\n"
                    "- read: 读取文件内容\n"
                    "- glob: 按模式搜索文件(支持**递归匹配，如 '**/*.py' 或 'dir/**')\n"
                    "- grep: 按内容搜索文件\n"
                    "- bash: 执行cmd命令(白名单内命令，Windows下为cmd.exe，请使用cmd语法，默认在工作目录下执行)\n"
                    "- write/edit: 写入或编辑文件\n"
                    "- web_search/web_browse: 网络搜索和浏览\n"
                    "\n重要规则:\n"
                    "1. 复杂任务必须先用todolist规划，避免盲目探索\n"
                    "2. 工具调用失败时，不要重复尝试同一方法，应换思路\n"
                    "3. 探索项目结构时，先用glob搜索文件列表，再用read读取关键文件"
                )
                system_prompt_parts.append(tool_guidance)

            system_msg = {"role": "system", "content": "\n".join(system_prompt_parts)}

            # 2.6 设置加载的文件夹为工具额外允许访问的目录
            loaded_folder_abs = os.path.abspath(loaded_folder) if loaded_folder and os.path.isdir(loaded_folder) else None
            tool_reg = config.tool_registry
            # 无加载文件夹时允许D盘根目录（bash默认工作目录）
            fallback_allowed = [loaded_folder_abs] if loaded_folder_abs else ["D:\\"]
            for tool in tool_reg.get_all().values():
                tool.allowed_folders = fallback_allowed

            # 3. 加载对话历史
            chat_file = os.path.join(BASE_DIR, "records", request.chat_id, "chat.json")
            if os.path.exists(chat_file):
                with open(chat_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            else:
                messages = []

            # 4. 构建给 AI 的用户消息（文本 + 文件内容）
            user_message_for_ai = request.message
            user_files_data = request.files or []
            if user_files_data:
                file_sections = []
                for f in user_files_data:
                    file_sections.append(
                        f"\n\n[附件文件: {f.get('name', '?')}]\n"
                        f"--- 内容 ---\n{f.get('content', '')}\n--- 结束 ---"
                    )
                user_message_for_ai = request.message + "".join(file_sections) if request.message else "".join(file_sections).strip()

            # 4.5 保存用户消息到历史（仅存文本，文件存为 metadata）
            user_msg_id = str(uuid.uuid4())[:8]
            user_msg_record = {"role": "user", "content": request.message, "id": user_msg_id}
            if user_files_data:
                # 存储不含 content 的轻量文件信息（前端渲染卡片用）
                user_msg_record["files"] = [
                    {"name": f.get("name", "?"), "size": f.get("size", 0)}
                    for f in user_files_data
                ]
                # 额外存储完整内容供前端弹窗使用（通过 API 单独获取或内联存储）
                user_msg_record["files_full"] = [
                    {"name": f.get("name", "?"), "size": f.get("size", 0), "content": f.get("content", "")}
                    for f in user_files_data
                ]
            messages.append(user_msg_record)

            # 5. 获取工具定义（过滤前端禁用的工具）
            disabled = set(request.disabled_tools or [])
            if request.tools_enabled and disabled:
                # 临时禁用前端指定的工具
                original_states = {}
                for name in disabled:
                    t = tool_reg.get(name)
                    if t:
                        original_states[name] = t.enabled
                        t.enabled = False
                tools = tool_reg.get_schemas()
                # 恢复原始状态
                for name, state in original_states.items():
                    t = tool_reg.get(name)
                    if t:
                        t.enabled = state
            elif request.tools_enabled:
                tools = tool_reg.get_schemas()
            else:
                tools = []

            # 停止检查回调
            def should_stop():
                return _stop_flags.get(request.chat_id, False)

            # ═══ 检查是否使用旧版思维链模式 ═══
            legacy_chain = cfg.get("legacy_chain", False)

            if legacy_chain:
                # ── 旧版思维链模式：使用 chainmode 四阶段管线 ──
                from openai import OpenAI
                from func.chainmode.agent_core import run_agent_pipeline

                base_url = PLATFORM_BASE_URLS.get(platform, "")
                client = OpenAI(api_key=api_key, base_url=base_url)

                # 从加载的文件夹收集文件路径（供 chainmode 读取）
                selected_files = []
                root_path = loaded_folder or ""
                if loaded_folder and os.path.isdir(loaded_folder):
                    for dirpath, dirnames, filenames in os.walk(loaded_folder):
                        # 过滤隐藏/无关目录
                        dirnames[:] = [d for d in dirnames
                                       if d.lower() not in {
                                           '__pycache__', '.git', 'node_modules',
                                           'env', 'venv', '.env', '.venv',
                                           '.idea', 'dist', 'build', 'target',
                                       }]
                        for fname in filenames:
                            selected_files.append(os.path.join(dirpath, fname))
                            if len(selected_files) >= 300:
                                break
                        if len(selected_files) >= 300:
                            break

                # 运行 chainmode 四阶段管线
                async for item in _run_legacy_chain(
                    client=client,
                    model=model,
                    platform=platform,
                    user_message=request.message,
                    selected_files=selected_files,
                    root_path=root_path,
                    thinking_level=thinking_level,
                    history=messages[:-1],  # 不含刚添加的用户消息（chainmode自己管理）
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt="\n".join(system_prompt_parts),
                    conversation_folder=request.chat_id,
                    agent_mode=agent_mode or "code",
                    should_stop=should_stop,
                ):
                    yield item

                # 保存对话历史（chainmode 的内容已 yield 给前端，这里保存简化记录）
                messages.append({"role": "assistant", "content": "[旧版思维链模式输出，请查看聊天内容]"})
                with open(chat_file, "w", encoding="utf-8") as f:
                    json.dump(messages, f, ensure_ascii=False, indent=2)
                return

            # ── 标准模式：使用 GoalExecutor 进行多轮工具调用 ──
            executor = GoalExecutor(
                tools_port=tools_port,
                tool_registry=tool_reg,
                tool_executor=config.tool_executor,
            )

            # 临时注入文件内容到用户消息，使 AI 能看到附件内容
            user_msg_index = len(messages) - 1  # 记录用户消息的固定索引
            clean_content = messages[user_msg_index]["content"]
            if user_files_data:
                messages[user_msg_index]["content"] = user_message_for_ai

            async for item in executor.execute(
                messages=messages,
                system_msg=system_msg,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking_level=thinking_level,
                should_stop=should_stop,
                chat_file=chat_file,
            ):
                yield item

            # 恢复干净文本（用固定索引，避免 executor 追加消息后 messages[-1] 指向错误的元素）
            if user_files_data:
                messages[user_msg_index]["content"] = clean_content

            # 7. 处理停止信号
            if executor.result.get("stopped"):
                with open(chat_file, "w", encoding="utf-8") as f:
                    json.dump(messages, f, ensure_ascii=False, indent=2)
                _stop_flags.pop(request.chat_id, None)
                yield "\n\n*[输出已停止]*"
                return

            # 8. 保存对话历史
            with open(chat_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)

        except Exception as e:
            yield f"[错误] {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")
