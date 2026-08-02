"""
共享配置与全局状态
"""
import os
import sys
import json

# 添加项目根目录到路径
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLED_DIR = sys._MEIPASS
    # 首次运行时从打包资源复制默认文件到exe旁
    for _d in ['config', 'wallpapers', os.path.join('frontend', 'dist')]:
        _dst = os.path.join(BASE_DIR, _d)
        _src = os.path.join(BUNDLED_DIR, _d)
        if not os.path.exists(_dst) and os.path.exists(_src):
            import shutil
            if os.path.isdir(_src):
                shutil.copytree(_src, _dst)
            else:
                os.makedirs(os.path.dirname(_dst), exist_ok=True)
                shutil.copy2(_src, _dst)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    BUNDLED_DIR = BASE_DIR

sys.path.insert(0, BASE_DIR)

# 前端构建目录
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# 全局工具状态（由 startup.py 初始化）
tool_registry = None
tool_executor = None

# 配置缓存
config_cache = {}

# 停止标志：{chat_id: True}
_stop_flags = {}


def get_config_dict():
    """读取全局配置（返回dict）"""
    config_path = os.path.join(BASE_DIR, "config", "info.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # 返回默认配置
    from func.api.models import ConfigModel
    return ConfigModel().dict()


def save_config_dict(data: dict):
    """保存全局配置"""
    config_path = os.path.join(BASE_DIR, "config", "info.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
