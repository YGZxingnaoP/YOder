"""
阶段4测试 - TODOLIST工具
"""
import sys
import os

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from func.tools.registry import ToolRegistry
from func.tools.builtin import TodoListTool


def test_phase4():
    """测试阶段4: TODOLIST工具"""
    print("\n" + "="*60)
    print("阶段4测试: TODOLIST工具")
    print("="*60 + "\n")
    
    # 1. 注册工具
    registry = ToolRegistry(project_root=PROJECT_ROOT)
    
    print("[1/6] 注册TODOLIST工具...")
    registry.register(TodoListTool)
    
    enabled = registry.get_enabled()
    print(f"  成功注册 {len(enabled)} 个工具")
    assert len(enabled) == 1, "应该注册1个工具"
    
    # 2. 创建任务
    print("\n[2/6] 创建任务...")
    result = registry.execute("todolist", {
        "action": "create",
        "title": "分析用户需求",
        "description": "理解用户想要实现的功能",
        "priority": "high"
    })
    assert "任务已创建" in result
    print("  创建任务: 通过")
    
    result = registry.execute("todolist", {
        "action": "create",
        "title": "设计架构",
        "description": "规划系统结构和模块划分",
        "priority": "high"
    })
    print("  创建第2个任务: 通过")
    
    result = registry.execute("todolist", {
        "action": "create",
        "title": "编写代码",
        "description": "实现核心功能",
        "priority": "medium"
    })
    print("  创建第3个任务: 通过")
    
    # 3. 列出任务
    print("\n[3/6] 列出任务...")
    result = registry.execute("todolist", {"action": "list"})
    assert "任务列表" in result
    assert "分析用户需求" in result
    print("  列出任务: 通过")
    print("  输出预览:")
    for line in result.split('\n')[:10]:
        print(f"    {line}")
    
    # 4. 更新任务状态
    print("\n[4/6] 更新任务状态...")
    result = registry.execute("todolist", {
        "action": "update",
        "task_id": "task_1",
        "status": "completed"
    })
    assert "任务已更新" in result
    print("  更新为completed: 通过")
    
    result = registry.execute("todolist", {
        "action": "update",
        "task_id": "task_2",
        "status": "in_progress"
    })
    print("  更新为in_progress: 通过")
    
    # 5. 获取任务详情
    print("\n[5/6] 获取任务详情...")
    result = registry.execute("todolist", {
        "action": "get",
        "task_id": "task_1"
    })
    assert "任务详情" in result
    assert "分析用户需求" in result
    print("  获取详情: 通过")
    
    # 6. 检查完成情况
    print("\n[6/6] 检查完成情况...")
    todolist_tool = registry.get("todolist")
    completion = todolist_tool.check_completion()
    
    print(f"  总任务: {completion['total']}")
    print(f"  已完成: {completion['completed_count']}")
    print(f"  进度: {completion['progress']:.1f}%")
    print(f"  全部完成: {completion['completed']}")
    
    assert completion['total'] == 3
    assert completion['completed_count'] == 1
    assert not completion['completed']
    
    print("\n" + "="*60)
    print("阶段4测试完成! TODOLIST工具工作正常")
    print("="*60)


if __name__ == "__main__":
    test_phase4()
