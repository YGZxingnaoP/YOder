"""
工具注册中心 - 管理所有工具的注册、查询、配置
"""
import json
import os
from typing import Dict, List, Optional, Type, Any
from .base import BaseTool


class ToolRegistry:
    """工具注册中心"""
    
    def __init__(self, project_root: str = ""):
        """
        初始化工具注册中心
        
        Args:
            project_root: 项目根目录绝对路径
        """
        self.project_root = project_root
        self._tools: Dict[str, BaseTool] = {}
        self._config_path = os.path.join(project_root, "config", "tools.json")
    
    def register(self, tool_class: Type[BaseTool]) -> None:
        """
        注册工具类
        
        Args:
            tool_class: 工具类(继承自BaseTool)
        """
        tool_instance = tool_class(project_root=self.project_root)
        self._tools[tool_instance.name] = tool_instance
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具实例
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例,不存在则返回None
        """
        return self._tools.get(name)
    
    def get_all(self) -> Dict[str, BaseTool]:
        """
        获取所有已注册的工具
        
        Returns:
            工具名称到实例的映射
        """
        return self._tools.copy()
    
    def get_enabled(self) -> List[BaseTool]:
        """
        获取所有已启用的工具
        
        Returns:
            已启用工具列表
        """
        return [tool for tool in self._tools.values() if tool.enabled]
    
    def get_schemas(self, only_enabled: bool = True) -> List[Dict]:
        """
        获取工具的JSON Schema列表(供Tool Calls使用)
        
        Args:
            only_enabled: 是否只返回已启用的工具
            
        Returns:
            OpenAI Function Calling格式的工具定义列表
        """
        tools = self.get_enabled() if only_enabled else list(self._tools.values())
        return [tool.get_schema() for tool in tools]
    
    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        执行指定工具
        
        Args:
            name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        tool = self.get(name)
        if not tool:
            return f"错误: 工具 '{name}' 不存在"
        
        if not tool.enabled:
            return f"错误: 工具 '{name}' 已禁用"
        
        if not tool.validate_arguments(arguments):
            return f"错误: 工具 '{name}' 参数不合法"
        
        try:
            return tool.execute(arguments)
        except Exception as e:
            return f"工具执行失败: {str(e)}"
    
    def load_config(self) -> None:
        """
        从config/tools.json加载工具配置
        """
        if not os.path.exists(self._config_path):
            return
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            tools_config = config.get("tools", [])
            for tool_config in tools_config:
                name = tool_config.get("name")
                enabled = tool_config.get("enabled", True)
                
                tool = self.get(name)
                if tool:
                    tool.enabled = enabled
        except Exception as e:
            print(f"加载工具配置失败: {e}")
    
    def save_config(self) -> None:
        """
        保存工具配置到config/tools.json
        """
        config = {
            "tools": [
                {
                    "name": tool.name,
                    "enabled": tool.enabled
                }
                for tool in self._tools.values()
            ]
        }
        
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def set_enabled(self, name: str, enabled: bool) -> bool:
        """
        设置工具启用状态
        
        Args:
            name: 工具名称
            enabled: 是否启用
            
        Returns:
            是否成功
        """
        tool = self.get(name)
        if not tool:
            return False
        
        tool.enabled = enabled
        self.save_config()
        return True
