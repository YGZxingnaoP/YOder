import os
from typing import Dict

IGNORE_DIRS = {
    "__pycache__", ".git", ".svn", ".hg", "node_modules",
    "env", "venv", ".env", ".venv", "runtime",
    ".idea", ".vs", ".vscode", "dist", "build",
    ".gradle", ".mvn", "target", ".DS_Store",
}

def get_file_tree(folder_path: str) -> Dict:
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
                if item in IGNORE_DIRS:
                    continue
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
