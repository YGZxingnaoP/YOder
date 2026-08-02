"""
todolist 工具 - AI自主任务规划
"""
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from ..base import BaseTool


class TodoListTool(BaseTool):
    """TODOLIST工具 - AI自主规划和跟踪任务"""
    
    name = "todolist"
    description = "管理任务列表。支持创建任务、更新状态、删除任务、查看进度。AI应分析用户意图后自主创建任务计划,每完成一步更新状态。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": ["create", "update", "delete", "list", "get", "clear"]
            },
            "task_id": {
                "type": "string",
                "description": "任务ID (update/delete/get操作必需)"
            },
            "title": {
                "type": "string",
                "description": "任务标题 (create操作必需)"
            },
            "description": {
                "type": "string",
                "description": "任务描述 (create操作可选)"
            },
            "status": {
                "type": "string",
                "description": "任务状态 (update操作必需)",
                "enum": ["pending", "in_progress", "completed", "failed"]
            },
            "priority": {
                "type": "string",
                "description": "优先级 (create/update操作可选)",
                "enum": ["low", "medium", "high"]
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, project_root: str = ""):
        super().__init__(project_root)
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._counter = 0
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行TODOLIST操作"""
        action = arguments.get("action", "")
        
        if action == "create":
            return self._create_task(arguments)
        elif action == "update":
            return self._update_task(arguments)
        elif action == "delete":
            return self._delete_task(arguments)
        elif action == "list":
            return self._list_tasks()
        elif action == "get":
            return self._get_task(arguments)
        elif action == "clear":
            return self._clear_tasks()
        else:
            return f"错误: 未知操作 '{action}'"
    
    def _create_task(self, args: Dict[str, Any]) -> str:
        """创建任务"""
        title = args.get("title", "").strip()
        if not title:
            return "错误: 任务标题不能为空"
        
        self._counter += 1
        task_id = f"task_{self._counter}"
        
        task = {
            "id": task_id,
            "title": title,
            "description": args.get("description", ""),
            "status": "pending",
            "priority": args.get("priority", "medium"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        self._tasks[task_id] = task
        
        return f"任务已创建\nID: {task_id}\n标题: {title}"
    
    def _update_task(self, args: Dict[str, Any]) -> str:
        """更新任务状态"""
        task_id = args.get("task_id", "")
        if not task_id:
            return "错误: 必须提供task_id"
        
        if task_id not in self._tasks:
            return f"错误: 任务 '{task_id}' 不存在"
        
        task = self._tasks[task_id]
        
        # 更新状态
        if "status" in args:
            task["status"] = args["status"]
        
        # 更新标题
        if "title" in args:
            task["title"] = args["title"]
        
        # 更新描述
        if "description" in args:
            task["description"] = args["description"]
        
        # 更新优先级
        if "priority" in args:
            task["priority"] = args["priority"]
        
        task["updated_at"] = datetime.now().isoformat()
        
        return f"任务已更新\nID: {task_id}\n状态: {task['status']}"
    
    def _delete_task(self, args: Dict[str, Any]) -> str:
        """删除任务"""
        task_id = args.get("task_id", "")
        if not task_id:
            return "错误: 必须提供task_id"
        
        if task_id not in self._tasks:
            return f"错误: 任务 '{task_id}' 不存在"
        
        del self._tasks[task_id]
        return f"任务已删除: {task_id}"
    
    def _list_tasks(self) -> str:
        """列出所有任务"""
        if not self._tasks:
            return "任务列表为空"
        
        # 按状态分组统计
        stats = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
        for task in self._tasks.values():
            stats[task["status"]] = stats.get(task["status"], 0) + 1
        
        total = len(self._tasks)
        completed = stats["completed"]
        progress = (completed / total * 100) if total > 0 else 0
        
        # 格式化输出
        output = f"任务列表 ({completed}/{total} 完成, {progress:.1f}%)\n"
        output += "=" * 60 + "\n\n"
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_tasks = sorted(
            self._tasks.values(),
            key=lambda t: (priority_order.get(t["priority"], 1), t["created_at"])
        )
        
        for task in sorted_tasks:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[~]",
                "completed": "[x]",
                "failed": "[!]"
            }.get(task["status"], "[ ]")
            
            priority_icon = {
                "high": "!!!",
                "medium": "!!",
                "low": "!"
            }.get(task["priority"], "!!")
            
            output += f"{status_icon} {task['id']}: {task['title']}\n"
            if task["description"]:
                output += f"    {task['description']}\n"
            output += f"    优先级: {priority_icon} | 状态: {task['status']}\n\n"
        
        output += f"统计:\n"
        output += f"  待处理: {stats['pending']}\n"
        output += f"  进行中: {stats['in_progress']}\n"
        output += f"  已完成: {stats['completed']}\n"
        output += f"  失败: {stats['failed']}\n"
        
        return output
    
    def _get_task(self, args: Dict[str, Any]) -> str:
        """获取单个任务详情"""
        task_id = args.get("task_id", "")
        if not task_id:
            return "错误: 必须提供task_id"
        
        if task_id not in self._tasks:
            return f"错误: 任务 '{task_id}' 不存在"
        
        task = self._tasks[task_id]
        
        output = f"任务详情\n"
        output += "=" * 60 + "\n\n"
        output += f"ID: {task['id']}\n"
        output += f"标题: {task['title']}\n"
        output += f"描述: {task['description'] or '无'}\n"
        output += f"状态: {task['status']}\n"
        output += f"优先级: {task['priority']}\n"
        output += f"创建时间: {task['created_at']}\n"
        output += f"更新时间: {task['updated_at']}\n"
        
        return output
    
    def _clear_tasks(self) -> str:
        """清空所有任务"""
        count = len(self._tasks)
        self._tasks.clear()
        return f"已清空 {count} 个任务"
    
    def get_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务(供外部调用)"""
        return list(self._tasks.values())
    
    def check_completion(self) -> Dict[str, Any]:
        """检查任务完成情况"""
        if not self._tasks:
            return {"completed": True, "progress": 0}
        
        total = len(self._tasks)
        completed = sum(1 for t in self._tasks.values() if t["status"] == "completed")
        failed = sum(1 for t in self._tasks.values() if t["status"] == "failed")
        
        return {
            "completed": completed + failed == total,
            "progress": (completed / total * 100) if total > 0 else 0,
            "total": total,
            "completed_count": completed,
            "failed_count": failed
        }

