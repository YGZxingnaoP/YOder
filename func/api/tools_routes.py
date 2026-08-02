"""
工具管理路由（/api/tools）
"""
from fastapi import APIRouter, HTTPException

from func.api import config

router = APIRouter()


@router.get("/api/tools")
async def list_tools():
    """获取工具列表及状态"""
    if not config.tool_registry:
        raise HTTPException(status_code=500, detail="工具系统未初始化")

    tools = []
    for tool in config.tool_registry.get_all().values():
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "permission": tool.permission,
            "enabled": tool.enabled
        })

    return {"tools": tools}


@router.post("/api/tools/{tool_name}/toggle")
async def toggle_tool(tool_name: str):
    """启用/禁用工具（持久化到tools.json）"""
    if not config.tool_registry:
        raise HTTPException(status_code=500, detail="工具系统未初始化")

    tool = config.tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具 {tool_name} 不存在")

    tool.enabled = not tool.enabled
    config.tool_registry.save_config()

    return {"status": "success", "enabled": tool.enabled}
