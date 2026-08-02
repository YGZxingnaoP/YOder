"""
GLM Tools Port - 智谱GLM模型 Tool Calls 适配
"""
import json
from openai import OpenAI
from typing import Callable, Dict, Any, List


class GLMToolsPort:
    """智谱GLM模型Tool Calls专用接口"""
    
    def __init__(self, api_key: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4/"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.platform = "智谱"
    
    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        callback: Callable[[str, str], None] = None,
        model: str = "glm-4-plus",
        max_tokens: int = 65536,
        temperature: float = 0.7,
        stop_check: Callable[[], bool] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带工具调用的对话
        
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
            # GLM支持tool_stream,与Qwen类似
            params = {
                "model": model,
                "messages": messages,
                "tools": tools if tools else None,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                "extra_body": {"thinking": {"type": "enabled"}}
            }
            
            completion = self.client.chat.completions.create(**params)
            
            content_parts = []
            thinking_parts = []
            tool_calls_dict = {}
            has_started_content = False
            
            for chunk in completion:
                if stop_check and stop_check():
                    break
                
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                
                # 处理思考内容
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
                
                # 处理工具调用 - GLM支持tool_stream直接拼接
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tool_call_delta in delta.tool_calls:
                        idx = tool_call_delta.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        
                        if tool_call_delta.id:
                            tool_calls_dict[idx]["id"] = tool_call_delta.id
                        
                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls_dict[idx]["function"]["name"] += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                tool_calls_dict[idx]["function"]["arguments"] += tool_call_delta.function.arguments
            
            tool_calls = [tool_calls_dict[idx] for idx in sorted(tool_calls_dict.keys())]
            
            return {
                "content": "".join(content_parts),
                "thinking": "".join(thinking_parts),
                "tool_calls": tool_calls,
                "finish_reason": "tool_calls" if tool_calls else "stop"
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
