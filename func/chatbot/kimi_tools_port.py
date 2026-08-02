"""
Kimi Tools Port - Kimi模型 Tool Calls 适配 (需要手动拼接delta)
"""
import json
from openai import OpenAI
from typing import Callable, Dict, Any, List


class KimiToolsPort:
    """Kimi模型Tool Calls专用接口"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.moonshot.cn/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.platform = "Kimi"
    
    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        callback: Callable[[str, str], None] = None,
        model: str = "moonshot-v1-128k",
        max_tokens: int = 65536,
        temperature: float = 0.7,
        stop_check: Callable[[], bool] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带工具调用的对话
        
        注意: Kimi需要手动拼接delta.tool_calls,与Qwen/GLM的tool_stream不同
        
        Args:
            messages: 对话消息列表
            tools: 工具定义列表(OpenAI Function Calling格式)
            callback: 回调函数 (event_type, data)
            model: 模型名称
            max_tokens: 最大输出token数
            temperature: 温度参数
            stop_check: 停止检查函数
            
        Returns:
            {
                "content": str,
                "thinking": str,
                "tool_calls": List[Dict],
                "finish_reason": str
            }
        """
        try:
            # Kimi标准流式,工具调用需要手动拼接
            params = {
                "model": model,
                "messages": messages,
                "tools": tools if tools else None,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            
            completion = self.client.chat.completions.create(**params)
            
            content_parts = []
            thinking_parts = []
            tool_calls_dict = {}  # 手动拼接工具调用
            has_started_content = False
            finish_reason = "stop"
            
            for chunk in completion:
                if stop_check and stop_check():
                    break
                
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                chunk_finish_reason = chunk.choices[0].finish_reason
                
                if chunk_finish_reason:
                    finish_reason = chunk_finish_reason
                
                # 处理思考内容 (Kimi可能不支持)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    if not has_started_content:
                        if callback:
                            callback("thinking", delta.reasoning_content)
                        thinking_parts.append(delta.reasoning_content)
                
                # 处理文本内容
                if hasattr(delta, "content") and delta.content:
                    if not has_started_content:
                        has_started_content = True
                    if callback:
                        callback("content", delta.content)
                    content_parts.append(delta.content)
                
                # 处理工具调用 - Kimi需要手动拼接
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tool_call_delta in delta.tool_calls:
                        idx = tool_call_delta.index
                        
                        # 初始化
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        
                        # 拼接ID
                        if tool_call_delta.id:
                            tool_calls_dict[idx]["id"] = tool_call_delta.id
                        
                        # 拼接函数名和参数
                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls_dict[idx]["function"]["name"] += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                tool_calls_dict[idx]["function"]["arguments"] += tool_call_delta.function.arguments
            
            # 整理结果
            tool_calls = [tool_calls_dict[idx] for idx in sorted(tool_calls_dict.keys())]
            
            # 判断结束原因
            if tool_calls:
                finish_reason = "tool_calls"
            
            return {
                "content": "".join(content_parts),
                "thinking": "".join(thinking_parts),
                "tool_calls": tool_calls,
                "finish_reason": finish_reason
            }
            
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ['data_inspection', 'content_filter', 'inappropriate content', 'content policy', 'safety', 'blocked', 'moderation']):
                if callback:
                    callback("error", "输入内容触发了 API 内容安全审查，请检查输入内容后重试。")
            else:
                if callback:
                    callback("error", str(e))
            
            return {
                "content": "",
                "thinking": "",
                "tool_calls": [],
                "finish_reason": "error"
            }
