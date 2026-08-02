"""
read 工具 - 读取文件内容(带安全限制)
"""
import os
from typing import Dict, Any
from ..base import BaseTool


class ReadTool(BaseTool):
    """读取文件内容工具"""
    
    name = "read"
    description = "读取指定文件的指定行范围内容。可自由指定任意行范围,默认读取整个文件。仅允许读取代码文件和文本文件,禁止读取敏感配置文件。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件的绝对路径或相对于项目根目录的路径"
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号(从1开始,默认1即文件开头)"
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号(包含,默认读取到文件末尾。可自由指定任意值,如100、500、1000或更大)"
            }
        },
        "required": ["file_path"]
    }
    
    # 白名单: 允许读取的文件扩展名
    ALLOWED_EXTENSIONS = {
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".hpp",
        ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
        ".html", ".css", ".scss", ".less",
        ".xml", ".csv", ".log",
        ".sh", ".bat", ".ps1",
        ".sql", ".graphql",
        ".vue", ".jsx", ".tsx",
        ".rs", ".go", ".rb", ".php"
    }
    
    # 黑名单: 禁止读取的文件/目录模式
    BLOCKED_PATTERNS = [
        "config/",
        ".env",
        "secrets",
        "api_key",
        "password",
        "token",
        "credential",
        ".git/",
        "node_modules/",
        "__pycache__/",
        ".pyc",
        ".exe",
        ".dll",
        ".so",
        ".dylib"
    ]
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行文件读取"""
        file_path = arguments.get("file_path", "")
        start_line = arguments.get("start_line", 1)
        end_line = arguments.get("end_line", 999999)  # 默认读取整个文件
        
        # 转换为绝对路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.project_root, file_path)
        
        abs_path = os.path.abspath(file_path)
        
        # 1. 路径验证: 必须在项目目录或允许的文件夹内
        if not self.is_path_allowed(abs_path):
            return "错误: 禁止访问项目目录外的文件"
        
        # 2. 文件存在性检查
        if not os.path.exists(abs_path):
            return f"错误: 文件不存在 - {abs_path}"
        
        if not os.path.isfile(abs_path):
            return f"错误: 不是文件 - {abs_path}"
        
        # 3. 扩展名验证
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return f"错误: 不支持读取 {ext} 类型文件,仅支持代码和文本文件"
        
        # 4. 黑名单验证 (统一使用正斜杠比较)
        rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in rel_path.lower():
                return f"错误: 禁止读取敏感文件/目录 - {rel_path}"
        
        # 5. 读取文件
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 验证行范围
            if start_line < 1:
                start_line = 1
            if end_line > len(lines):
                end_line = len(lines)
            if start_line > end_line:
                return "错误: start_line 不能大于 end_line"
            
            # 提取指定行范围
            selected_lines = lines[start_line - 1:end_line]
            content = "".join(selected_lines)
            
            # 格式化输出
            result = f"文件: {rel_path}\n"
            result += f"行范围: {start_line}-{end_line} (共 {len(selected_lines)} 行)\n"
            result += f"总行数: {len(lines)}\n"
            result += "=" * 60 + "\n"
            result += content
            
            return result
            
        except UnicodeDecodeError:
            return f"错误: 文件编码不是UTF-8,无法读取 - {abs_path}"
        except Exception as e:
            return f"读取失败: {str(e)}"
