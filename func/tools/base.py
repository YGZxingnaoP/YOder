"""
工具基类 - 所有工具的抽象基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseTool(ABC):
    """工具基类"""
    
    # 工具名称(唯一标识)
    name: str = ""
    
    # 工具描述(供AI理解用途)
    description: str = ""
    
    # 参数JSON Schema定义
    parameters: Dict[str, Any] = {}
    
    # 工具分类(safe/moderate/dangerous)
    permission: str = "safe"
    
    # 是否启用
    enabled: bool = True
    
    def __init__(self, project_root: str = ""):
        """
        初始化工具
        
        Args:
            project_root: 项目根目录绝对路径
        """
        self.project_root = project_root
        self.allowed_folders: list = []  # 额外允许访问的文件夹列表
    
    def is_path_allowed(self, abs_path: str) -> bool:
        """检查绝对路径是否在允许范围内（项目根目录或额外允许的文件夹）"""
        import os
        # 检查项目根目录
        if abs_path == self.project_root or abs_path.startswith(self.project_root + os.sep):
            return True
        # 检查额外允许的文件夹
        for folder in self.allowed_folders:
            if abs_path == folder or abs_path.startswith(folder + os.sep):
                return True
        return False
    
    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> str:
        """
        执行工具
        
        Args:
            arguments: 工具参数字典
            
        Returns:
            工具执行结果字符串
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的JSON Schema定义(供Tool Calls使用)
        
        Returns:
            OpenAI Function Calling格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        验证参数是否符合schema
        
        Args:
            arguments: 待验证的参数
            
        Returns:
            是否合法
        """
        required = self.parameters.get("required", [])
        for param in required:
            if param not in arguments:
                return False
        return True
