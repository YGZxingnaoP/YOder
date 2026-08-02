"""
taskprests - 阶段二任务填充的输出格式预设集合

每个预设定义了 AI 填充 task 时必须遵守的输出格式约束，
用于防止多版本输出、格式混乱等问题。

预设列表：
- python: Python 代码
- batch: Windows 批处理脚本
- yaml: YAML 配置文件
- json: JSON 配置文件
- markdown: Markdown 文档
- plaintext: 纯文本
- csv: CSV 数据
- mixed: 混合格式（代码+说明混合）
"""

from . import presets
from .presets import get_preset, wrap_with_fence, needs_code_fence, get_fence_language

__all__ = ["presets", "get_preset", "wrap_with_fence", "needs_code_fence", "get_fence_language"]
