"""
write 工具 - 创建或覆盖文件
"""
import os
from typing import Dict, Any
from ..base import BaseTool


class WriteTool(BaseTool):
    """写入文件工具"""
    
    name = "write"
    description = "创建新文件或覆盖现有文件的全部内容。会自动创建不存在的父目录。"
    permission = "moderate"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件的绝对路径或相对于项目根目录的路径"
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容"
            }
        },
        "required": ["file_path", "content"]
    }
    
    # 黑名单: 禁止写入的文件/目录模式
    BLOCKED_PATTERNS = [
        "config/",
        ".env",
        "secrets",
        ".git/",
        "node_modules/",
        "__pycache__/"
    ]
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行文件写入"""
        file_path = arguments.get("file_path", "")
        content = arguments.get("content", "")
        
        # 转换为绝对路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.project_root, file_path)
        
        abs_path = os.path.abspath(file_path)
        
        # 1. 路径验证: 必须在项目目录内
        if not abs_path.startswith(self.project_root):
            return "错误: 禁止在项目目录外创建文件"
        
        # 2. 黑名单验证 (统一使用正斜杠比较)
        rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in rel_path.lower():
                return f"错误: 禁止写入敏感文件/目录 - {rel_path}"
        
        # 3. 创建父目录
        try:
            parent_dir = os.path.dirname(abs_path)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
        except Exception as e:
            return f"错误: 无法创建目录 - {str(e)}"
        
        # 4. 写入文件
        try:
            # 检查是否是覆盖现有文件
            is_overwrite = os.path.exists(abs_path)
            
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # 统计信息
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            char_count = len(content)
            
            if is_overwrite:
                result = f"成功: 已覆盖文件 - {rel_path}\n"
            else:
                result = f"成功: 已创建文件 - {rel_path}\n"
            
            result += f"行数: {line_count}\n"
            result += f"字符数: {char_count}\n"
            
            return result
            
        except Exception as e:
            return f"写入失败: {str(e)}"
