"""
files_reader/locate.py
递归扫描文件夹，返回树状结构字典。
"""
import os
from typing import Dict, List

def get_file_tree(folder_path: str) -> Dict:
    """
    返回文件夹的树状结构。
    格式：
    {
        "name": "文件夹名",
        "type": "directory",
        "path": "绝对路径",
        "children": [ ...文件或子目录... ]
    }
    文件节点：
    {
        "name": "文件名",
        "type": "file",
        "path": "绝对路径"
    }
    """
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"{folder_path} 不是有效目录")

    def _build(path):
        name = os.path.basename(path)
        if os.path.isdir(path):
            children = []
            try:
                items = sorted(os.listdir(path))
            except PermissionError:
                items = []
            for item in items:
                full = os.path.join(path, item)
                children.append(_build(full))
            return {
                "name": name,
                "type": "directory",
                "path": os.path.abspath(path),
                "children": children
            }
        else:
            return {
                "name": name,
                "type": "file",
                "path": os.path.abspath(path)
            }

    return _build(folder_path)