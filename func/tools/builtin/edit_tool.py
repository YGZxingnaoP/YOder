"""
edit 工具 - 精确文本替换
"""
import os
import difflib
from typing import Dict, Any
from ..base import BaseTool


class EditTool(BaseTool):
    """精确文本替换工具"""
    
    name = "edit"
    description = "在文件中进行精确的文本替换。需要提供旧文本和新文本,会完全匹配旧文本并替换为新文本。"
    permission = "moderate"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件的绝对路径或相对于项目根目录的路径"
            },
            "old_text": {
                "type": "string",
                "description": "要被替换的旧文本(必须完全匹配)"
            },
            "new_text": {
                "type": "string",
                "description": "替换后的新文本"
            }
        },
        "required": ["file_path", "old_text", "new_text"]
    }
    
    # 黑名单: 禁止修改的文件/目录模式
    BLOCKED_PATTERNS = [
        "config/",
        ".env",
        "secrets",
        ".git/",
        "node_modules/",
        "__pycache__/"
    ]
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行文本替换"""
        file_path = arguments.get("file_path", "")
        old_text = arguments.get("old_text", "")
        new_text = arguments.get("new_text", "")
        
        # 转换为绝对路径
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.project_root, file_path)
        
        abs_path = os.path.abspath(file_path)
        
        # 1. 路径验证: 必须在项目目录内
        if not abs_path.startswith(self.project_root):
            return "错误: 禁止修改项目目录外的文件"
        
        # 2. 文件存在性检查
        if not os.path.exists(abs_path):
            return f"错误: 文件不存在 - {abs_path}"
        
        if not os.path.isfile(abs_path):
            return f"错误: 不是文件 - {abs_path}"
        
        # 3. 黑名单验证 (统一使用正斜杠比较)
        rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in rel_path.lower():
                return f"错误: 禁止修改敏感文件/目录 - {rel_path}"
        
        # 4. 读取文件
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except UnicodeDecodeError:
            return f"错误: 文件编码不是UTF-8,无法修改 - {abs_path}"
        except Exception as e:
            return f"读取失败: {str(e)}"
        
        # 5. 查找旧文本
        if old_text not in original_content:
            # 尝试找到相似的文本
            lines = original_content.split("\n")
            similar_lines = difflib.get_close_matches(old_text, lines, n=3, cutoff=0.6)
            
            result = f"错误: 在文件中未找到完全匹配的文本\n"
            result += f"文件: {rel_path}\n"
            
            if similar_lines:
                result += f"可能相似的文本:\n"
                for i, line in enumerate(similar_lines, 1):
                    result += f"  {i}. {line[:100]}{'...' if len(line) > 100 else ''}\n"
            
            return result
        
        # 6. 计算替换次数
        count = original_content.count(old_text)
        if count > 1:
            return f"警告: 找到 {count} 处匹配的文本,请提供更多上下文以确保唯一性"
        
        # 7. 执行替换
        new_content = original_content.replace(old_text, new_text, 1)
        
        # 8. 写回文件
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            # 计算变更统计
            old_lines = original_content.split("\n")
            new_lines = new_content.split("\n")
            
            result = f"成功: 已修改文件 - {rel_path}\n"
            result += f"替换次数: 1\n"
            result += f"原行数: {len(old_lines)}\n"
            result += f"新行数: {len(new_lines)}\n"
            
            # 显示变更前后对比(如果行数不多)
            if len(old_lines) < 20 and len(new_lines) < 20:
                result += "\n变更前后对比:\n"
                result += "=" * 60 + "\n"
                result += "旧内容:\n"
                result += old_text[:200] + "...\n" if len(old_text) > 200 else old_text + "\n"
                result += "-" * 60 + "\n"
                result += "新内容:\n"
                result += new_text[:200] + "...\n" if len(new_text) > 200 else new_text + "\n"
            
            return result
            
        except Exception as e:
            return f"写入失败: {str(e)}"
