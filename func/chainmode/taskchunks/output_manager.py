"""
output_manager.py - output.json 读写管理
管理 records/对话文件夹/temp/output.json 的 CRUD 操作。
"""
import json
import os
import re
from typing import Optional, Dict

from ..taskprests.presets import wrap_with_fence, needs_code_fence, CODE_FENCE_MAP


class OutputManager:
    """
    管理 output.json 文件。

    结构:
    {
        "framework": "完整框架文本（task_n 随填充被替换）",
        "tasks": {
            "task1": {
                "status": "pending" | "filled" | "error",
                "description": "详细任务描述",
                "files": ["文件路径列表"],
                "requirements": "任务要求提示词",
                "content": "填充后的内容",
                "retry_count": 0,
                "review_feedback": ""
            },
            ...
        }
    }
    """

    def __init__(self, temp_dir: str):
        """
        Args:
            temp_dir: records/对话文件夹/temp/ 的绝对路径
        """
        self.temp_dir = temp_dir
        self.output_path = os.path.join(temp_dir, "output.json")
        self.principle_path = os.path.join(temp_dir, "principle.json")
        self._data: Optional[Dict] = None
        self._principle: Optional[Dict] = None

    def initialize(self, framework: str = "", tasks: dict = None):
        """初始化 output.json"""
        self._data = {
            "framework": framework,
            "tasks": tasks or {}
        }
        self.save()

    def load(self) -> Dict:
        """从磁盘加载 output.json"""
        if self._data is not None:
            return self._data
        if os.path.isfile(self.output_path):
            with open(self.output_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {"framework": "", "tasks": {}}
        return self._data

    def save(self):
        """保存到磁盘"""
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_framework(self) -> str:
        """获取当前框架文本"""
        data = self.load()
        return data.get("framework", "")

    def set_framework(self, framework: str):
        """设置框架文本"""
        data = self.load()
        data["framework"] = framework
        self.save()

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取指定 task"""
        data = self.load()
        return data.get("tasks", {}).get(task_id)

    def update_task(self, task_id: str, **kwargs):
        """更新指定 task 的字段"""
        data = self.load()
        if task_id not in data["tasks"]:
            data["tasks"][task_id] = {}
        data["tasks"][task_id].update(kwargs)
        self.save()

    def _get_display_content(self, task: dict) -> str:
        """获取 task 的显示内容（根据 preset 自动包裹代码围栏）"""
        content = task.get("content", "")
        if not content:
            return content
        preset = task.get("preset", "mixed")
        return wrap_with_fence(content, preset)
    
    def fill_task(self, task_id: str, content: str):
        """填充 task 内容，替换框架中的 [task_n] 占位符"""
        data = self.load()
        if task_id in data["tasks"]:
            data["tasks"][task_id]["status"] = "filled"
            data["tasks"][task_id]["content"] = content
        # 替换框架中的占位符
        placeholder = f"[{task_id}]"
        if placeholder in data["framework"]:
            # 根据 preset 类型自动包裹代码围栏
            task = data["tasks"].get(task_id, {})
            display_content = self._get_display_content(task)
            replacement = display_content
            # 如果内容是多行或含代码块，且占位符处于行内位置（前面有非空白字符），
            # 在内容前添加换行，避免代码块紧跟在行内文字后面导致 markdown 渲染异常
            if ('\n' in display_content or '```' in display_content):
                pattern = r'(\S)([ \t]*)' + re.escape(placeholder)
                match = re.search(pattern, data["framework"])
                if match:
                    replacement = '\n' + display_content
            data["framework"] = data["framework"].replace(placeholder, replacement)
            # 去重兆底：消除替换后产生的连续重复标题行
            data["framework"] = self._dedup_headings(data["framework"])
        self.save()

    @staticmethod
    def _dedup_headings(text: str) -> str:
        """消除连续重复的 Markdown 标题行"""
        lines = text.split('\n')
        result = []
        prev_heading = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                if stripped == prev_heading:
                    # 跳过重复标题
                    continue
                prev_heading = stripped
            else:
                if stripped == '':
                    # 空行不重置 prev_heading（标题之间可能隔一个空行）
                    pass
                else:
                    prev_heading = None
            result.append(line)
        return '\n'.join(result)

    def restore_task_placeholder(self, task_id: str):
        """恢复 task 在框架中的占位符（用于重做前）"""
        data = self.load()
        task = data.get("tasks", {}).get(task_id)
        if not task:
            return
        # 直接恢复 task 占位符
        display_content = self._get_display_content(task)
        if display_content and display_content in data["framework"]:
            data["framework"] = data["framework"].replace(display_content, f"[{task_id}]")
        else:
            content = task.get("content", "")
            if content and content in data["framework"]:
                data["framework"] = data["framework"].replace(content, f"[{task_id}]")
        self.save()

    def mark_error(self, task_id: str, feedback: str):
        """标记 task 为错误状态，记录审查反馈"""
        data = self.load()
        if task_id in data["tasks"]:
            task = data["tasks"][task_id]
            task["status"] = "error"
            task["review_feedback"] = feedback
            task["retry_count"] = task.get("retry_count", 0) + 1
        self.save()

    def get_all_tasks(self) -> Dict:
        """获取所有 task"""
        data = self.load()
        return data.get("tasks", {})

    def get_pending_tasks(self) -> list:
        """获取所有 pending 状态的 task_id（按插入顺序）"""
        data = self.load()
        result = []
        for tid, task in data.get("tasks", {}).items():
            if task.get("status") == "pending":
                result.append(tid)
        return result

    def get_final_output(self) -> str:
        """获取最终的完整输出（framework 文本，含格式修正和文件列表）"""
        data = self.load()
        output = data.get("framework", "")
        if not output:
            return output

        tasks = data.get("tasks", {})

        # ── 后处理：修正内联多行内容的格式问题 ──
        # fill_task() 已对新的填充做了修正，但对历史数据（框架中占位符已替换、
        # 多行内容仍然内联）需要再处理一次。
        # 策略：将已填充的内容临时还原为占位符 → 修正占位符位置 → 重新替换回内容
        output = self._fix_inline_multiline(output, tasks)

        # ── 合并同预设代码围栏 ──
        # 当所有已填充的父级 task 使用相同的代码类预设时，Phase 1 框架中的
        # 非占位符部分（如 import 语句、Flask 配置）不会被代码围栏包裹，
        # 导致 markdown 渲染时这些代码显示为普通文本。
        # 此步骤将整个框架合并为一个代码围栏，确保所有代码正确渲染。
        output = self._merge_same_preset_fences(output, tasks)

        # ── 添加生成的文件列表 ──
        file_entries = []
        for tid, task in tasks.items():
            task_files = task.get("files", [])
            content = task.get("content", "")
            if task_files and content:
                for f in task_files:
                    if f not in file_entries:
                        file_entries.append(f)

        if file_entries:
            file_list_lines = "\n".join(f"- `{f}`" for f in file_entries)
            output += f"\n\n---\n## 📁 生成的文件\n\n{file_list_lines}"

        return output

    @staticmethod
    def _is_framework_code_like(text: str) -> bool:
        """
        判断框架文本中非围栏部分是否主要为代码（而非 markdown 说明文本）。
        用于决定是否将整个框架合并为一个代码围栏。
        """
        # 先移除已有的代码围栏块
        stripped = re.sub(r'```[\s\S]*?```', '', text)
        lines = [l.strip() for l in stripped.split('\n') if l.strip()]
        if not lines:
            return True

        # 代码特征：import 语句、from...import、赋值、函数/类定义
        code_indicators = sum(1 for l in lines if any(
            l.startswith(p) for p in (
                'import ', 'from ', 'def ', 'class ',
                'app.', 'if ', '#', '@', 'try:', 'except',
                'os.', 'sys.', 'return ',
            )
        ))

        # markdown 特征：## 标题、列表、加粗
        md_indicators = sum(1 for l in lines if any(
            l.startswith(p) for p in ('##', '**', '- ', '* ', '> ')
        ) if not l.startswith('#!'))

        return code_indicators >= md_indicators

    def _merge_same_preset_fences(self, text: str, tasks: dict) -> str:
        """
        当所有已填充的父级 task 使用相同的代码类预设时，
        将框架中的独立代码围栏合并为一个统一的围栏，
        避免框架中的非围栏代码（如 import）显示为普通文本。
        """
        filled_tasks = {tid: t for tid, t in tasks.items()
                        if t.get('content')}
        if not filled_tasks:
            return text

        # 检查是否所有 task 使用相同的代码类预设
        presets = set(t.get('preset', 'mixed') for t in filled_tasks.values())
        if len(presets) != 1:
            return text

        preset = presets.pop()
        if not needs_code_fence(preset):
            return text

        # 检查框架中的非围栏部分是否主要为代码
        if not self._is_framework_code_like(text):
            return text

        # 获取围栏语言标识
        fence_lang = CODE_FENCE_MAP.get(preset, "")

        # 收集每个 task 的围栏内容并剥离围栏
        for tid, task in filled_tasks.items():
            dc = self._get_display_content(task)
            if not dc:
                continue

            stripped = dc.strip()
            # 剥离 ```language ... ``` 围栏
            if stripped.startswith('```') and stripped.endswith('```') and len(stripped) > 6:
                inner_lines = stripped.split('\n')
                if len(inner_lines) >= 2:
                    raw_content = '\n'.join(inner_lines[1:-1])
                    text = text.replace(dc, raw_content, 1)

        # 将整个框架包裹在统一的代码围栏中
        text = text.strip()
        text = f'```{fence_lang}\n{text}\n```'

        return text

    def _fix_inline_multiline(self, text: str, tasks: dict) -> str:
        """
        修正框架中内联多行内容的格式问题。

        当 task 占位符原本处于行内位置（如 "- file.py: [task2]"），
        而填充内容为多行文本或代码块时，替换后会导致 markdown 渲染异常。
        此方法检测并修正这种情况，在每个内联多行内容前插入换行。
        同时根据 preset 类型自动包裹代码围栏。
        """
        # 预计算每个 task 的显示内容（含围栏包裹）
        display_contents = {}
        for tid, task in tasks.items():
            if task.get("content"):
                display_contents[tid] = self._get_display_content(task)

        # 第一步：将已填充的内容还原为占位符（按内容长度降序，防止子串误匹配）
        sorted_tasks = sorted(
            [(tid, t) for tid, t in tasks.items() if tid in display_contents],
            key=lambda x: len(display_contents[x[0]]),
            reverse=True
        )
        for tid, task in sorted_tasks:
            dc = display_contents[tid]
            placeholder = f"[{tid}]"
            if dc in text:
                text = text.replace(dc, placeholder, 1)
            else:
                # 回退：尝试原始内容（历史数据可能未包裹围栏）
                raw = task.get("content", "")
                if raw and raw != dc and raw in text:
                    text = text.replace(raw, placeholder, 1)

        # 第二步：对每个占位符检测是否处于行内位置，若是则补换行
        for tid, task in sorted_tasks:
            dc = display_contents[tid]
            placeholder = f"[{tid}]"
            if placeholder not in text:
                continue
            if '\n' in dc or '```' in dc:
                pattern = r'(\S)([ \t]*)' + re.escape(placeholder)
                match = re.search(pattern, text)
                if match:
                    text = re.sub(
                        pattern,
                        lambda m: m.group(1) + '\n' + m.group(2) + placeholder,
                        text
                    )

        # 第三步：将占位符替换回显示内容（含围栏）
        for tid, task in sorted_tasks:
            placeholder = f"[{tid}]"
            text = text.replace(placeholder, display_contents[tid])

        return text

    # ── principle.json 读写 ──

    def get_principle(self) -> Dict:
        """获取编写准则"""
        if self._principle is not None:
            return self._principle
        if os.path.isfile(self.principle_path):
            with open(self.principle_path, "r", encoding="utf-8") as f:
                self._principle = json.load(f)
        else:
            self._principle = {}
        return self._principle

    def set_principle(self, principle: Dict):
        """保存编写准则"""
        self._principle = principle
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self.principle_path, "w", encoding="utf-8") as f:
            json.dump(principle, f, ensure_ascii=False, indent=2)

    def get_principle_text(self) -> str:
        """将准则转为可读文本，用于注入 task prompt"""
        p = self.get_principle()
        if not p:
            return "(无编写准则)"
        # 使用结构化格式输出，让 AI 更容易理解和遵循
        lines = ["以下是所有 task 必须严格遵循的编写准则："]
        for section, content in p.items():
            section_name = {
                "data_structures": "📦 数据结构规范",
                "function_signatures": "🔧 函数签名规范",
                "config_schemas": "📝 配置结构规范",
                "data_flow": "🔄 数据流转路径",
                "expression_conventions": "💡 表达式约定",
                "naming": "🏷️ 命名规范",
                "conventions": "✅ 跨任务一致性规则",
                "terminology": "📚 术语统一",
                "style": "✍️ 风格规范",
                "cross_references": "🔗 交叉引用约束",
            }.get(section, section)
            lines.append(f"\n### {section_name}")
            if isinstance(content, dict):
                for key, val in content.items():
                    if isinstance(val, dict):
                        lines.append(f"- **{key}**:")
                        for k2, v2 in val.items():
                            lines.append(f"  - {k2}: {v2}")
                    else:
                        lines.append(f"- **{key}**: {val}")
            elif isinstance(content, list):
                for i, item in enumerate(content, 1):
                    lines.append(f"{i}. {item}")
            else:
                lines.append(str(content))
        return "\n".join(lines)
