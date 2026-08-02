"""
bash 工具 - 执行shell命令(白名单+用户确认)
"""
import os
import subprocess
import shlex
from typing import Dict, Any, Callable, Optional
from ..base import BaseTool


class BashTool(BaseTool):
    """Shell命令执行工具"""
    
    name = "bash"
    description = "执行cmd命令（Windows下为cmd.exe）。仅允许白名单内的安全命令,危险命令会被拒绝。执行前会提示用户确认。"
    permission = "dangerous"
    
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的cmd命令"
            },
            "working_dir": {
                "type": "string",
                "description": "命令执行的工作目录(默认项目根目录)"
            }
        },
        "required": ["command"]
    }
    
    # 白名单: 允许执行的命令(前缀匹配)
    ALLOWED_COMMANDS = [
        # 查看命令
        "ls", "dir", "pwd", "cd",
        "cat", "type", "more", "head", "tail",
        "find", "where", "which",
        "grep", "findstr",
        "tree",
        
        # 文件操作
        "mkdir", "rmdir",
        "cp", "copy",
        "mv", "move",
        
        # 系统信息
        "echo", "print",
        "date", "time",
        "whoami", "hostname",
        
        # Python相关
        "python", "python3", "py",
        "pip", "pip3",
        
        # Node.js相关
        "node", "npm", "npx", "yarn",
        
        # Git命令
        "git",
        
        # 编译工具
        "gcc", "g++", "make", "cmake",
        
        # 其他
        "curl", "wget",
        "tar", "gzip", "7z"
    ]
    
    # 黑名单: 绝对禁止的命令(包含即拒绝)
    BLOCKED_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "del /f /s /q",
        "format",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",  # Fork炸弹
        "shutdown",
        "reboot",
        "poweroff",
        "sudo",
        "su",
        "passwd",
        "useradd",
        "userdel"
    ]
    
    def __init__(self, project_root: str = "", confirm_callback: Optional[Callable[[str], bool]] = None):
        """
        初始化bash工具
        
        Args:
            project_root: 项目根目录
            confirm_callback: 用户确认回调函数,接收命令字符串,返回是否允许执行
        """
        super().__init__(project_root)
        self.confirm_callback = confirm_callback
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行shell命令"""
        command = arguments.get("command", "")
        working_dir = arguments.get("working_dir", "")
        
        # 1. 命令非空检查
        if not command.strip():
            return "错误: 命令不能为空"
        
        # 2. 黑名单检查
        command_lower = command.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in command_lower:
                return f"错误: 禁止执行危险命令 - {pattern}"
        
        # 3. 解析命令,提取主命令
        try:
            parts = shlex.split(command, posix=False)
            if not parts:
                return "错误: 无法解析命令"
            
            main_cmd = parts[0].lower()
            # 移除路径前缀(如 /usr/bin/ls -> ls)
            main_cmd = os.path.basename(main_cmd)
            
        except Exception as e:
            return f"错误: 命令解析失败 - {str(e)}"
        
        # 4. 白名单检查
        is_allowed = False
        for allowed in self.ALLOWED_COMMANDS:
            if main_cmd == allowed or main_cmd.startswith(allowed):
                is_allowed = True
                break
        
        if not is_allowed:
            return (
                f"错误: 命令 '{main_cmd}' 不在白名单内\n"
                f"允许的命令: {', '.join(self.ALLOWED_COMMANDS[:10])}...\n"
                f"如需执行其他命令,请在UI中手动确认"
            )
        
        # 5. 用户确认(如果有回调)
        if self.confirm_callback:
            if not self.confirm_callback(command):
                return "用户拒绝执行此命令"
        
        # 6. 设置工作目录
        if working_dir:
            if not os.path.isabs(working_dir):
                base = self.allowed_folders[0] if getattr(self, 'allowed_folders', None) and self.allowed_folders[0] else "D:\\"
                working_dir = os.path.join(base, working_dir)
            cwd = os.path.abspath(working_dir)
        else:
            # 默认使用加载的文件夹（如果有），否则使用D盘根目录
            if getattr(self, 'allowed_folders', None) and self.allowed_folders[0]:
                cwd = self.allowed_folders[0]
            else:
                cwd = "D:\\"
        
        # 路径验证
        if not self.is_path_allowed(cwd):
            return "错误: 工作目录必须在项目目录内"
        
        if not os.path.exists(cwd):
            return f"错误: 工作目录不存在 - {cwd}"
        
        # 7. 执行命令
        try:
            # Windows下使用cmd.exe
            if os.name == "nt":
                full_command = f'cmd /c "{command}"'
            else:
                full_command = command
            
            process = subprocess.Popen(
                full_command,
                cwd=cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            
            # 设置超时(30秒)
            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                return "错误: 命令执行超时(30秒)"
            
            # 格式化输出
            result = f"命令: {command}\n"
            result += f"工作目录: {os.path.relpath(cwd, self.project_root)}\n"
            result += f"退出码: {process.returncode}\n"
            result += "=" * 60 + "\n"
            
            if stdout:
                result += "标准输出:\n"
                result += stdout
                result += "\n"
            
            if stderr:
                result += "标准错误:\n"
                result += stderr
            
            if process.returncode != 0:
                result += f"\n警告: 命令以非零退出码结束 ({process.returncode})\n"
            
            return result
            
        except Exception as e:
            return f"执行失败: {str(e)}"
