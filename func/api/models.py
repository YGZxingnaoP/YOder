"""
Pydantic 数据模型
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ConfigModel(BaseModel):
    platform: str = "阿里"
    model: str = "qwen-max"
    max_tokens: int = 65536
    temperature: float = 0.7
    thinking_level: str = "high"
    memory_rounds: int = 50
    legacy_chain: bool = False
    tools_enabled: bool = True
    agent_mode: str = ""
    api_keys: Dict[str, str] = {}


class ChatConfigModel(BaseModel):
    """对话级配置覆盖"""
    platform: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    thinking_level: Optional[str] = None
    agent_mode: Optional[str] = None


class ChatRequest(BaseModel):
    chat_id: str
    message: str
    tools_enabled: bool = True
    disabled_tools: List[str] = []
    agent_mode: str = ""
    loaded_folder: Optional[str] = None  # 前端加载的文件夹路径
    files: List[dict] = []  # 附件: [{"name":"x.py","size":1234,"content":"..."}]


class SummarizeRequest(BaseModel):
    chat_id: str
    max_chars: Optional[int] = None


class MemoryConfigModel(BaseModel):
    enabled: bool = False
    max_summary_chars: int = 2000


class CreateChatRequest(BaseModel):
    name: str


class RenameChatRequest(BaseModel):
    name: str


class SaveFilesRequest(BaseModel):
    path: str
    tree: Optional[List[Any]] = None
