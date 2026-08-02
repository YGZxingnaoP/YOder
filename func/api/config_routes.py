"""
全局配置路由（/api/config）
"""
from fastapi import APIRouter

from func.api.config import get_config_dict, save_config_dict
from func.api.models import ConfigModel

router = APIRouter()


@router.get("/api/config")
async def get_config():
    """获取配置"""
    return get_config_dict()


@router.post("/api/config")
async def save_config(config: ConfigModel):
    """保存配置"""
    save_config_dict(config.dict())
    return {"status": "success"}
