"""
GoalExecutor - 目标驱动异步执行器
基于渐进式软限制的多轮工具调用管理,替代 main.py 中的内联循环
"""
import asyncio
import json
from typing import Dict, Any, List, Callable, Optional


class GoalExecutor:
    """
    异步目标驱动执行器 - 管理多轮工具调用循环
    
    渐进式软限制策略:
    - 第1-9轮: 自由调用工具
    - 第10轮: 软警告,提醒AI评估进度
    - 第12轮: 要求AI输出阶段性分析(仍可调用工具)
    - 第14-15轮: 最后冲刺窗口
    - 第16轮: 强制移除工具,要求最终总结
    """
    
    # 限制参数
    MAX_ITERATIONS = 16        # 最大迭代次数
    WARN_ROUND = 10            # 软警告轮次
    ANALYSIS_ROUND = 12        # 分析轮次
    FINAL_WINDOW_START = 14    # 最后窗口开始
    HARD_LIMIT = 16            # 硬性限制
    
    def __init__(
        self,
        tools_port,
        tool_registry,
        tool_executor,
    ):
        self.tools_port = tools_port
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.result = {}  # 执行结果, 调用方在 async for 结束后读取
    
    async def execute(
        self,
        messages: List[Dict[str, Any]],
        system_msg: Dict[str, str],
        tools: List[Dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        thinking_level: str = "high",
        should_stop: Callable[[], bool] = None,
        chat_file: str = "",
    ) -> Dict[str, Any]:
        """
        异步执行多轮工具调用循环, 流式 yield 协议标记
        
        协议标记:
        - \\x01 + text: thinking内容
        - \\x02 + text: 正文内容
        - \\x03 + JSON: 工具调用信息 {name, arguments}
        - \\x04 + JSON: 工具执行结果 {id, content}
        
        Returns:
            {
                "stopped": bool,      # 是否被用户停止
                "tool_calls": int,    # 总工具调用轮数
                "iterations": int,    # 实际迭代次数
            }
        """
        if should_stop is None:
            should_stop = lambda: False
        
        iteration = 0
        tool_round = 0
        stopped = False
        
        while iteration < self.MAX_ITERATIONS:
            if should_stop():
                stopped = True
                break
            
            iteration += 1
            
            # ═══ 根据轮次构建工具列表 + 注入渐进式提示 ═══
            current_tools = tools
            extra_messages = []
            
            if tool_round >= self.HARD_LIMIT:
                # 硬性限制: 移除所有工具, 强制输出最终文本
                current_tools = []
                extra_messages.append({
                    "role": "system",
                    "content": (
                        f"[系统指令] 工具调用已达{self.HARD_LIMIT}轮硬性上限。"
                        "不允许再调用任何工具。请基于以上所有工具返回的结果，直接给出最终总结回复。"
                    )
                })
            elif tool_round >= self.FINAL_WINDOW_START:
                # 最后窗口: 仍可用工具, 但提示收尾
                extra_messages.append({
                    "role": "system",
                    "content": (
                        f"[系统提示] 工具调用已达{tool_round}轮，接近上限。"
                        "请尽快收尾。如果关键信息已获取，建议直接输出分析结果。"
                        "如仍需调用工具，请高效完成。"
                    )
                })
            elif tool_round >= self.ANALYSIS_ROUND:
                # 分析节点: 要求输出阶段性分析
                extra_messages.append({
                    "role": "system",
                    "content": (
                        f"[系统提示] 工具调用已达{tool_round}轮。"
                        "请先输出一段阶段性分析，总结已获得的关键信息。"
                        "然后评估：如果信息仍不充足，可继续调用工具；如果已充足，输出最终回复。"
                    )
                })
            elif tool_round >= self.WARN_ROUND:
                # 软警告
                extra_messages.append({
                    "role": "system",
                    "content": (
                        f"[系统提示] 工具调用已达{tool_round}轮，请注意控制调用次数，高效完成任务。"
                    )
                })
            
            # ═══ 调用AI ═══
            current_messages = [system_msg] + messages + extra_messages
            
            # _call_ai 是异步生成器, 通过实例属性 _ai_result 传递结果
            queue = asyncio.Queue()
            async for item in self._call_ai(
                queue=queue,
                messages=current_messages,
                tools=current_tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking_level=thinking_level,
                should_stop=should_stop,
            ):
                yield item
            result = self._ai_result
            
            # 检查停止信号
            if should_stop():
                stopped = True
                partial = result.get("content", "")
                if partial:
                    messages.append({"role": "assistant", "content": partial})
                    if result.get("thinking"):
                        messages[-1]["thinking"] = result["thinking"]
                break
            
            # ═══ 处理AI响应 ═══
            if result["tool_calls"]:
                tool_round += 1
                
                # yield \x03: 工具调用信息
                for tc in result["tool_calls"]:
                    fn = tc.get("function", {})
                    yield "\x03" + json.dumps({
                        "name": fn.get("name", "unknown"),
                        "arguments": fn.get("arguments", "")
                    }, ensure_ascii=False)
                
                # 执行工具
                tool_messages = self.tool_executor.execute_tool_calls(result["tool_calls"])
                
                # yield \x04: 工具执行结果
                for tool_msg in tool_messages:
                    yield "\x04" + json.dumps({
                        "id": tool_msg.get("tool_call_id", ""),
                        "content": tool_msg.get("content", "")[:50000]
                    }, ensure_ascii=False)
                
                # 添加到消息历史
                assistant_msg = {
                    "role": "assistant",
                    "content": result["content"],
                    "tool_calls": result["tool_calls"]
                }
                if result.get("thinking"):
                    assistant_msg["thinking"] = result["thinking"]
                messages.append(assistant_msg)
                messages.extend(tool_messages)
                
                # 检查TODOLIST完成状态
                todolist_tool = self.tool_registry.get("todolist")
                if todolist_tool:
                    try:
                        completion = todolist_tool.check_completion()
                        if completion.get("completed") and completion.get("total", 0) > 0:
                            # TODOLIST全部完成, 退出循环
                            break
                    except Exception:
                        pass
                
                continue
            else:
                # 无工具调用 → 最终响应
                messages.append({"role": "assistant", "content": result["content"]})
                if result.get("thinking"):
                    messages[-1]["thinking"] = result["thinking"]
                
                # 若首轮就无工具调用且内容为空，给用户一个提示
                if not result["content"].strip() and tool_round == 0:
                    if result.get("thinking"):
                        fallback = "[AI思考后未产出内容，请重试]"
                    else:
                        fallback = "[AI未给出回复，请重试]"
                    messages.append({"role": "assistant", "content": fallback})
                    yield "\x02" + fallback
                break
        
        # 将结果存入实例属性 (async generator不能用return带值)
        self.result = {
            "stopped": stopped,
            "tool_calls": tool_round,
            "iterations": iteration,
        }
    
    async def _call_ai(
        self,
        queue: asyncio.Queue,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        thinking_level: str,
        should_stop: Callable[[], bool],
    ) -> Dict[str, Any]:
        """
        调用AI, 将同步的chat_with_tools桥接到asyncio Queue,
        由回调函数将thinking/content标记推入queue, 
        返回AI调用结果Dict
        """
        def callback(event_type, data):
            if event_type == "thinking":
                queue.put_nowait("\x01" + data)
            elif event_type == "content":
                queue.put_nowait("\x02" + data)
        
        loop = asyncio.get_event_loop()
        
        bg_task = loop.run_in_executor(
            None,
            lambda: self.tools_port.chat_with_tools(
                messages=messages,
                tools=tools if tools else None,
                callback=callback,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking_level=thinking_level,
                stop_check=should_stop,
            )
        )
        
        # 实时流式输出: 轮询queue直到后台任务完成
        while not bg_task.done():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                if item is not None:
                    yield item
            except asyncio.TimeoutError:
                continue
        
        # 清空队列中剩余项
        queue.put_nowait(None)
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
        
        # 通过实例属性传递AI调用结果 (async generator不能用return带值)
        self._ai_result = bg_task.result()
