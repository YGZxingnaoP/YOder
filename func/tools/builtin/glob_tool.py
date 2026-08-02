"""
glob 工具 - 按模式搜索文件
"""
import os
import fnmatch
from typing import Dict, Any, List
from ..base import BaseTool


class GlobTool(BaseTool):
    """按模式搜索文件工具"""
    
    name = "glob"
    description = "按文件名模式搜索文件,返回匹配的文件路径列表及文件信息。支持通配符(*, **, ?, [])。其中 ** 表示递归匹配所有子目录。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "文件名模式,支持通配符。例如: '*.py', '**/*.py', 'src/*.js', 'test_*.txt'。使用 ** 递归匹配子目录。"
            },
            "directory": {
                "type": "string",
                "description": "搜索的起始目录(默认项目根目录)"
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
        ".pip_cache"
    }
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行文件搜索"""
        pattern = arguments.get("pattern", "")
        directory = arguments.get("directory", "")
        max_results = arguments.get("max_results", 50)
        
        # 设置搜索目录
        if directory:
            if not os.path.isabs(directory):
                directory = os.path.join(self.project_root, directory)
            search_dir = os.path.abspath(directory)
        else:
            search_dir = self.project_root
        
        # 路径验证
        if not self.is_path_allowed(search_dir):
            return "错误: 禁止搜索项目目录外的文件"
        
        if not os.path.exists(search_dir):
            return f"错误: 目录不存在 - {search_dir}"
        
        # 搜索文件
        matched_files: List[str] = []
        
        # 检测是否是 ** 递归模式
        is_recursive = "**" in pattern
        
        if is_recursive:
            # 处理各种 ** 模式
            # dir/** -> 匹配 dir 下所有文件
            # **/*.py -> 匹配所有 .py 文件
            # dir/**/*.py -> 匹配 dir 下所有 .py 文件（含子目录）
            # ** -> 匹配所有文件
            if pattern.endswith("/**"):
                # dir/** 格式: 限定子目录的递归搜索
                dir_prefix = pattern[:-3]  # 去掉 /**
                file_pattern = "*"
            elif pattern.startswith("**/"):
                # **/*.py 格式: 全局递归匹配特定文件
                file_pattern = pattern[3:]  # 去掉 **/
                if file_pattern == "":
                    file_pattern = "*"
            elif pattern == "**":
                file_pattern = "*"
            elif "/**/" in pattern:
                # dir/**/*.ext 格式: 限定子目录的递归搜索 + 文件过滤
                # 使用完整相对路径匹配，将 ** 替换为 * 以兼容 fnmatch
                match_pattern = pattern.replace("**", "*")
                file_pattern = None  # 标记使用路径匹配而非文件名匹配
            else:
                # 其他含 ** 的模式，尝试提取文件名部分
                file_pattern = pattern.replace("**/", "").replace("/**", "")
                if not file_pattern:
                    file_pattern = "*"
        else:
            file_pattern = pattern
        
        try:
            for root, dirs, files in os.walk(search_dir, topdown=True):
                # 过滤黑名单目录
                dirs[:] = [d for d in dirs if d not in self.BLOCKED_DIRS]
                
                # 匹配文件
                for filename in files:
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, search_dir).replace("\\", "/")
                    
                    if is_recursive:
                        if pattern.endswith("/**") and '/' in pattern[:-3]:
                            # dir/** 格式: 检查文件是否在指定子目录下
                            dir_prefix = pattern[:-3]
                            matched = rel_path.startswith(dir_prefix + "/") or rel_path.startswith(dir_prefix + "\\")
                        elif pattern.endswith("/**"):
                            # 顶层 dir/** 格式
                            dir_prefix = pattern[:-3]
                            matched = rel_path.startswith(dir_prefix + "/")
                        elif file_pattern is None:
                            # dir/**/*.ext 格式: 用完整相对路径匹配
                            matched = fnmatch.fnmatch(rel_path, match_pattern)
                        else:
                            # **/*.ext 等格式: 只匹配文件名
                            matched = fnmatch.fnmatch(filename, file_pattern)
                    else:
                        # 普通模式：
                        if '/' in pattern or '\\' in pattern:
                            # 带路径的模式（如 src/*.py）
                            matched = fnmatch.fnmatch(rel_path, pattern.replace("\\", "/"))
                        else:
                            # 只匹配文件名
                            matched = fnmatch.fnmatch(filename, pattern)
                    
                    if matched:
                        matched_files.append((rel_path, abs_path))
                        
                        # 限制结果数量
                        if len(matched_files) >= max_results:
                            break
                
                if len(matched_files) >= max_results:
                    break
            
            # 格式化输出
            if not matched_files:
                return f"未找到匹配的文件\n模式: {pattern}\n目录: {os.path.relpath(search_dir, self.project_root)}"
            
            result = f"找到 {len(matched_files)} 个匹配文件\n"
            result += f"模式: {pattern}\n"
            result += f"目录: {os.path.relpath(search_dir, self.project_root)}\n"
            result += "=" * 60 + "\n"
            
            for i, (rel_path, abs_path) in enumerate(matched_files, 1):
                # 获取文件元数据（借鉴 ai-agent-python）
                try:
                    size = os.path.getsize(abs_path)
                    size_str = self._format_size(size)
                    result += f"{i}. {rel_path} ({size_str})\n"
                except OSError:
                    result += f"{i}. {rel_path}\n"
            
            if len(matched_files) == max_results:
                result += f"\n(已达到最大结果数 {max_results}，可能存在更多匹配)\n"
            
            return result
            
        except Exception as e:
            return f"搜索失败: {str(e)}"
    
    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f}GB"
