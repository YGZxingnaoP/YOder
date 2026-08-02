"""
端到端测试 - 完整系统测试
测试所有组件集成
"""
import sys
import os

# 添加项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from func.tools.registry import ToolRegistry
from func.tools.executor import ToolExecutor
from func.tools.builtin import (
    ReadTool, WriteTool, EditTool, GlobTool, GrepTool, BashTool,
    WebSearchTool, WebBrowseTool, EdgeCheckTool, TodoListTool
)
from func.chatbot.tools_port_factory import ToolsPortFactory
from func.agent.goal_executor import GoalExecutor
from func.agent.agent_worker import AgentWorker


def test_complete_system():
    """端到端系统测试"""
    print("\n" + "="*70)
    print("YOder 端到端系统测试")
    print("="*70 + "\n")
    
    # 1. 测试工具注册
    print("[1/5] 测试工具系统...")
    registry = ToolRegistry(project_root=PROJECT_ROOT)
    
    registry.register(ReadTool)
    registry.register(WriteTool)
    registry.register(EditTool)
    registry.register(GlobTool)
    registry.register(GrepTool)
    registry.register(BashTool)
    registry.register(WebSearchTool)
    registry.register(WebBrowseTool)
    registry.register(EdgeCheckTool)
    registry.register(TodoListTool)
    
    tools = registry.get_enabled()
    print(f"  注册工具数: {len(tools)}")
    assert len(tools) == 10, "应该注册10个工具"
    print("  工具系统: 通过")
    
    # 2. 测试工具执行器
    print("\n[2/5] 测试工具执行器...")
    executor = ToolExecutor(registry)
    
    result = registry.execute("todolist", {
        "action": "create",
        "title": "测试任务",
        "priority": "high"
    })
    assert "任务已创建" in result
    print("  工具执行器: 通过")
    
    # 3. 测试ToolsPort工厂
    print("\n[3/5] 测试ToolsPort工厂...")
    test_key = "test_key_123"
    
    qwen_port = ToolsPortFactory.create("阿里", test_key)
    deepseek_port = ToolsPortFactory.create("DeepSeek", test_key)
    kimi_port = ToolsPortFactory.create("Kimi", test_key)
    glm_port = ToolsPortFactory.create("智谱", test_key)
    
    assert qwen_port and deepseek_port and kimi_port and glm_port
    print("  ToolsPort工厂: 通过")
    
    # 4. 测试GoalExecutor
    print("\n[4/5] 测试GoalExecutor...")
    goal_executor = GoalExecutor(
        tools_port=qwen_port,
        tool_registry=registry,
        tool_executor=executor
    )
    
    assert goal_executor.max_iterations == 20
    print("  GoalExecutor初始化: 通过")
    
    # 5. 测试AgentWorker
    print("\n[5/5] 测试AgentWorker...")
    config = {
        "project_root": PROJECT_ROOT,
        "platform": "阿里",
        "model": "qwen-max",
        "api_keys": {"阿里": test_key},
        "max_tokens": 65536,
        "temperature": 0.7,
        "legacy_chain": False
    }
    
    agent_worker = AgentWorker(config)
    assert agent_worker.legacy_chain == False
    assert len(agent_worker.get_todolist()) == 0
    
    # 测试模式切换
    agent_worker.toggle_legacy_mode()
    assert agent_worker.legacy_chain == True
    print("  AgentWorker: 通过")
    
    print("\n" + "="*70)
    print("端到端测试全部通过!")
    print("="*70)
    
    # 统计信息
    print("\n系统统计:")
    print(f"  内置工具: {len(tools)} 个")
    print(f"  模型适配: 4 个平台")
    print(f"  核心组件: GoalExecutor + AgentWorker")
    print(f"  配置文件: config/tools.json")


if __name__ == "__main__":
    test_complete_system()
