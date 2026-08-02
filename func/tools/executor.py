"""
工具执行器 - 处理Tool Calls循环,执行工具并回传结果
"""
import json
from typing import List, Dict, Any, Callable, Optional
from .registry import ToolRegistry


class ToolExecutor:
    """工具执行器"""
    
    def __init__(self, registry: ToolRegistry):
        """
        初始化工具执行器
        
        Args:
            registry: 工具注册中心
        """
        self.registry = registry
    
    def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行多个工具调用
        
        Args:
            tool_calls: 模型返回的tool_calls列表
            progress_callback: 进度回调函数 callback(tool_name, status)
            
        Returns:
            tool messages列表(用于回传给模型)
        """
        tool_messages = []
        
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            name = function.get("name")
            arguments_str = function.get("arguments", "{}")
            
            # 解析参数
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}
            
            # 通知进度: 开始执行
            if progress_callback:
                progress_callback(name, "executing")
            
            # 执行工具
            result = self.registry.execute(name, arguments)
            
            # 通知进度: 执行完成
            if progress_callback:
                progress_callback(name, "completed")
            
            # 构造tool message
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": result
            })
        
        return tool_messages
    
    def process_stream_tool_calls(
        self,
        tool_calls_buffer: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        处理流式输出中累积的tool_calls
        
        Args:
            tool_calls_buffer: 流式累积的tool_calls缓冲区
            progress_callback: 进度回调函数
            
        Returns:
            tool messages列表
        """
        # 过滤出完整的tool_calls(有name和完整arguments的)
        complete_tool_calls = []
        for tc in tool_calls_buffer:
            function = tc.get("function", {})
            if function.get("name") and function.get("arguments"):
                complete_tool_calls.append(tc)
        
        return self.execute_tool_calls(complete_tool_calls, progress_callback)
