"""
task_manager.py - Task 列表管理与遍历
负责 task 的有序遍历、子任务展开、tasklist UI 数据生成。
"""
from typing import List, Dict, Optional


def build_task_order(tasks: Dict) -> List[str]:
    """
    按照父-子层级关系，返回有序的 task_id 列表。
    父任务按插入顺序排列，每个父任务后面紧跟其子任务（递归）。
    """
    result = []
    for tid, task in tasks.items():
        if not task.get("parent"):
            _collect_task(tid, tasks, result, set())
    return result


def _collect_task(tid: str, tasks: Dict, result: List[str], visited: set):
    """递归收集 task 及其子任务"""
    if tid in visited:
        return
    visited.add(tid)
    result.append(tid)
    task = tasks.get(tid, {})
    for child_id in task.get("children", []):
        _collect_task(child_id, tasks, result, visited)


def build_tasklist_for_ui(tasks: Dict) -> list:
    """
    构建用于 UI chain-progress 显示的 tasklist 数据。
    返回 [{"text": "task1: 描述...", "status": "pending|active|done", "indent": 0}, ...]
    """
    order = build_task_order(tasks)
    result = []
    for tid in order:
        task = tasks.get(tid, {})
        desc = task.get("description", tid)
        status = task.get("status", "pending")
        parent = task.get("parent")
        indent = 1 if parent else 0
        # 映射状态
        if status == "filled":
            ui_status = "done"
        elif status == "error":
            ui_status = "active"  # 显示为重做中
        else:
            ui_status = "pending"
        display_text = f"{tid}: {desc}"
        result.append({
            "text": display_text,
            "status": ui_status,
            "indent": indent,
            "id": tid
        })
    return result


def mark_task_active(tasklist: list, active_tid: str):
    """将指定 task 标记为 active 状态（用于 UI 显示当前正在处理的 task）"""
    for item in tasklist:
        if item["id"] == active_tid:
            item["status"] = "active"
            break


def get_pending_leaf_tasks(tasks: Dict) -> List[str]:
    """
    获取所有 pending 状态的叶子任务（无子任务的或子任务都已完成的）。
    按遍历顺序返回。
    """
    order = build_task_order(tasks)
    result = []
    for tid in order:
        task = tasks.get(tid, {})
        if task.get("status") == "pending":
            result.append(tid)
    return result


def count_tasks(tasks: Dict) -> Dict[str, int]:
    """统计各状态的任务数"""
    counts = {"pending": 0, "filled": 0, "error": 0, "total": 0}
    for tid, task in tasks.items():
        counts["total"] += 1
        status = task.get("status", "pending")
        if status in counts:
            counts[status] += 1
    return counts
