"""
AgentWorker - 重构后的Agent工作器
集成GoalExecutor,支持TODOLIST驱动和旧版思维链切换
"""
import json
from typing import Dict, Any, List, Callable, Optional
from func.agent.goal_executor import GoalExecutor
from func.tools.registry import ToolRegistry
from func.tools.executor import ToolExecutor
from func.chatbot.tools_port_factory import ToolsPortFactory


class AgentWorker:
    """Agent工作器 - 统一管理新旧两种模式"""
    
    def __init__(
        self,
        config: Dict[str, Any],
        progress_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.config = config
        self.progress_callback = progress_callback
        
        # 初始化工具系统
        self.tool_registry = ToolRegistry(project_root=config.get("project_root", ""))
        self._register_builtin_tools()
        self.tool_executor = ToolExecutor(self.tool_registry)
        
        # 初始化ToolsPort
        platform = config.get("platform", "阿里")
        api_key = config.get("api_keys", {}).get(platform, "")
        self.tools_port = ToolsPortFactory.create(platform=platform, api_key=api_key)
        
        # 初始化GoalExecutor
        self.goal_executor = GoalExecutor(
            tools_port=self.tools_port,
            tool_registry=self.tool_registry,
            tool_executor=self.tool_executor,
            progress_callback=progress_callback
        )
        
        # 模式选择
        self.legacy_chain = config.get("legacy_chain", False)
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        from func.tools.builtin import (
            ReadTool, WriteTool, EditTool, GlobTool, GrepTool, BashTool,
            WebSearchTool, WebBrowseTool, EdgeCheckTool, TodoListTool
        )
        
        self.tool_registry.register(ReadTool)
        self.tool_registry.register(WriteTool)
        self.tool_registry.register(EditTool)
        self.tool_registry.register(GlobTool)
        self.tool_registry.register(GrepTool)
        self.tool_registry.register(BashTool)
        self.tool_registry.register(WebSearchTool)
        self.tool_registry.register(WebBrowseTool)
        self.tool_registry.register(EdgeCheckTool)
        self.tool_registry.register(TodoListTool)
    
    def process_message(
        self,
        user_message: str,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        处理用户消息
        
        Args:
            user_message: 用户消息
            messages: 对话历史
            
        Returns:
            {
                "content": str,
                "tool_calls": List[Dict],
                "mode": str,  # "goal_driven" 或 "legacy_chain"
                "todolist": List[Dict]
            }
        """
        if self.legacy_chain:
            # 旧版思维链模式(保留原有逻辑)
            return self._process_legacy(user_message, messages)
        else:
            # 新版TODOLIST驱动模式
            return self._process_goal_driven(user_message, messages)
    
    def _process_goal_driven(
        self,
        user_message: str,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """TODOLIST驱动模式"""
        
        if self.progress_callback:
            self.progress_callback("status", "开始目标驱动执行...")
        
        # 执行目标驱动
        result = self.goal_executor.execute(
            user_message=user_message,
            messages=messages,
            model=self.config.get("model", "qwen-max"),
            max_tokens=self.config.get("max_tokens", 65536),
            temperature=self.config.get("temperature", 0.7)
        )
        
        # 获取TODOLIST
        todolist = self.goal_executor.get_todolist()
        
        return {
            "content": result["content"],
            "tool_calls": result["tool_calls"],
            "mode": "goal_driven",
            "iterations": result["iterations"],
            "completed": result["completed"],
            "todolist": todolist
        }
    
    def _process_legacy(
        self,
        user_message: str,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """旧版思维链模式(调用原有四阶段管线)"""
        
        if self.progress_callback:
            self.progress_callback("status", "使用旧版思维链模式...")
        
        # 这里调用原有的agent_core逻辑
        # 为了简化,这里直接调用AI
        def callback(event_type, data):
            if self.progress_callback:
                self.progress_callback(event_type, data)
        
        result = self.tools_port.chat_with_tools(
            messages=messages,
            tools=[],  # 旧版不使用工具
            callback=callback,
            model=self.config.get("model", "qwen-max"),
            max_tokens=self.config.get("max_tokens", 65536),
            temperature=self.config.get("temperature", 0.7)
        )
        
        return {
            "content": result["content"],
            "tool_calls": [],
            "mode": "legacy_chain",
            "todolist": []
        }
    
    def toggle_legacy_mode(self, enabled: bool = None):
        """切换旧版模式"""
        if enabled is None:
            self.legacy_chain = not self.legacy_chain
        else:
            self.legacy_chain = enabled
        
        self.config["legacy_chain"] = self.legacy_chain
    
    def get_todolist(self) -> List[Dict[str, Any]]:
        """获取当前TODOLIST"""
        return self.goal_executor.get_todolist()
    
    def check_completion(self) -> Dict[str, Any]:
        """检查任务完成情况"""
        return self.goal_executor.check_todolist_status()
