"""
应用启动初始化（工具注册）
"""
from func.tools.registry import ToolRegistry
from func.tools.executor import ToolExecutor
from func.tools.builtin import (
    ReadTool, WriteTool, EditTool, GlobTool, GrepTool, BashTool,
    WebSearchTool, WebBrowseTool, EdgeCheckTool, TodoListTool
)
from func.api import config


def init_tools():
    """启动时初始化工具系统，挂载到 config 全局状态"""
    config.tool_registry = ToolRegistry(project_root=config.BASE_DIR)

    # 注册所有内置工具
    for tool_cls in (
        ReadTool, WriteTool, EditTool, GlobTool, GrepTool, BashTool,
        WebSearchTool, WebBrowseTool, EdgeCheckTool, TodoListTool,
    ):
        config.tool_registry.register(tool_cls)

    config.tool_executor = ToolExecutor(config.tool_registry)

    print(f"工具系统初始化完成,注册了 {len(config.tool_registry.get_enabled())} 个工具")

    # 加载持久化的工具开关配置
    config.tool_registry.load_config()
    print(f"加载工具配置后,启用了 {len(config.tool_registry.get_enabled())} 个工具")
