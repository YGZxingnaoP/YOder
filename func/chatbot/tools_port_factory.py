"""
Tools Port Factory - 模型工具调用工厂类
根据配置自动选择对应的ToolsPort
"""
import json
import os
from typing import Dict, Any, Optional
from .qwen_tools_port import QwenToolsPort
from .deepseek_tools_port import DeepSeekToolsPort
from .kimi_tools_port import KimiToolsPort
from .glm_tools_port import GLMToolsPort


PLATFORM_BASE_URLS = {
    "阿里": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "DeepSeek": "https://api.deepseek.com",
    "智谱": "https://open.bigmodel.cn/api/paas/v4/",
    "Kimi": "https://api.moonshot.cn/v1",
}


class ToolsPortFactory:
    """工具调用端口工厂类"""
    
    @staticmethod
    def create(
        platform: str,
        api_key: str,
        base_url: Optional[str] = None
    ):
        """
        创建对应平台的ToolsPort实例
        
        Args:
            platform: 平台名称 (阿里/DeepSeek/智谱/Kimi)
            api_key: API密钥
            base_url: 自定义base_url(可选)
            
        Returns:
            对应平台的ToolsPort实例
        """
        if not base_url:
            base_url = PLATFORM_BASE_URLS.get(platform, "")
        
        if not base_url:
            raise ValueError(f"未知平台: {platform}")
        
        if platform == "阿里":
            return QwenToolsPort(api_key=api_key, base_url=base_url)
        elif platform == "DeepSeek":
            return DeepSeekToolsPort(api_key=api_key, base_url=base_url)
        elif platform == "Kimi":
            return KimiToolsPort(api_key=api_key, base_url=base_url)
        elif platform == "智谱":
            return GLMToolsPort(api_key=api_key, base_url=base_url)
        else:
            raise ValueError(f"不支持的平台: {platform}")
    
    @staticmethod
    def create_from_config(config_path: str = None):
        """
        从配置文件创建ToolsPort实例
        
        Args:
            config_path: 配置文件路径(默认config/info.json)
            
        Returns:
            tuple: (ToolsPort实例, 当前配置)
        """
        if config_path is None:
            import sys
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, "config", "info.json")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        platform = config.get("platform", "阿里")
        api_keys = config.get("api_keys", {})
        api_key = api_keys.get(platform, "")
        
        if not api_key:
            raise ValueError(f"{platform} API Key 未配置")
        
        tools_port = ToolsPortFactory.create(platform=platform, api_key=api_key)
        return tools_port, config
