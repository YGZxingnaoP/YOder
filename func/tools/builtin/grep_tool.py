"""
grep 工具 - 正则搜索文件内容
"""
import os
import re
import fnmatch
from typing import Dict, Any, List, Tuple
from ..base import BaseTool


class GrepTool(BaseTool):
    """正则搜索文件内容工具"""
    
    name = "grep"
    description = "使用正则表达式搜索文件内容,返回匹配的行及行号。支持多文件搜索。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "正则表达式模式"
            },
            "file_pattern": {
                "type": "string",
                "description": "文件匹配模式(如'*.py', '*.js'),默认搜索所有文件"
            },
            "directory": {
                "type": "string",
                "description": "搜索的起始目录(默认项目根目录)"
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "是否区分大小写(默认true)"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数(默认50)"
            }
        },
        "required": ["pattern"]
    }
    
    # 黑名单: 禁止搜索的目录
    BLOCKED_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".idea",
        ".vscode",
        "config"
    }
    
    # 允许搜索的文件扩展名
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
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行正则搜索"""
        pattern = arguments.get("pattern", "")
        file_pattern = arguments.get("file_pattern", "*")
        directory = arguments.get("directory", "")
        case_sensitive = arguments.get("case_sensitive", True)
        max_results = arguments.get("max_results", 50)
        
        # 设置搜索目录
        if directory:
            if not os.path.isabs(directory):
                directory = os.path.join(self.project_root, directory)
            search_dir = os.path.abspath(directory)
        else:
            search_dir = self.project_root
        
        # 路径验证: 必须在允许范围内
        if not self.is_path_allowed(search_dir):
            return "错误: 禁止搜索项目目录外的文件"
        
        if not os.path.exists(search_dir):
            return f"错误: 目录不存在 - {search_dir}"
        
        # 编译正则表达式
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"错误: 无效的正则表达式 - {str(e)}"
        
        # 搜索文件
        results: List[Tuple[str, int, str]] = []  # (file_path, line_num, line_content)
        
        try:
            for root, dirs, files in os.walk(search_dir, topdown=True):
                # 过滤黑名单目录
                dirs[:] = [d for d in dirs if d not in self.BLOCKED_DIRS]
                
                # 匹配文件
                for filename in files:
                    if not fnmatch.fnmatch(filename, file_pattern):
                        continue
                    
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
                    
                    # 检查扩展名
                    ext = os.path.splitext(abs_path)[1].lower()
                    if ext not in self.ALLOWED_EXTENSIONS:
                        continue
                    
                    # 读取文件并搜索
                    try:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            for line_num, line in enumerate(f, 1):
                                if regex.search(line):
                                    results.append((rel_path, line_num, line.rstrip()))
                                    
                                    # 限制结果数量
                                    if len(results) >= max_results:
                                        break
                        
                        if len(results) >= max_results:
                            break
                            
                    except (UnicodeDecodeError, IOError):
                        # 跳过无法读取的文件
                        continue
                
                if len(results) >= max_results:
                    break
            
            # 格式化输出
            if not results:
                return f"未找到匹配的内容\n模式: {pattern}\n目录: {os.path.relpath(search_dir, self.project_root)}"
            
            result = f"找到 {len(results)} 个匹配\n"
            result += f"模式: {pattern}\n"
            result += f"目录: {os.path.relpath(search_dir, self.project_root)}\n"
            result += "=" * 60 + "\n"
            
            current_file = None
            for file_path, line_num, line_content in results:
                if file_path != current_file:
                    result += f"\n{file_path}:\n"
                    current_file = file_path
                
                # 截断过长的行
                display_line = line_content[:100] + "..." if len(line_content) > 100 else line_content
                result += f"  {line_num:5d}: {display_line}\n"
            
            if len(results) == max_results:
                result += f"\n(已达到最大结果数 {max_results},可能存在更多匹配)\n"
            
            return result
            
        except Exception as e:
            return f"搜索失败: {str(e)}"
