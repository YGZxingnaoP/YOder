"""
file_reader.py - 文件读取工具
禁止截断，完整读取文件内容。
"""
import os
from func.chatbot.message_build import read_file_as_content


def read_file_full(file_path: str) -> str:
    """
    读取文件完整内容（不截断），支持 PDF/DOCX/文本。
    返回文件的完整文本内容。
    """
    if not os.path.isfile(file_path):
        return f"[文件不存在: {file_path}]"
    block = read_file_as_content(file_path)
    if not block:
        return f"[文件读取为空: {file_path}]"
    if block.get("type") == "image_url":
        return f"[图片文件，无法以文本形式嵌入: {os.path.basename(file_path)}]"
    return block.get("text", f"[文件内容为空: {file_path}]")


def build_file_map(selected_files: list, root_path: str = ""):
    """
    构建文件路径映射表，支持多级模糊匹配。

    Returns:
        (file_list_text, file_map)
        file_map: {basename/relpath/lower -> abs_path}
    """
    file_list_text = ""
    file_map = {}
    for fpath in selected_files:
        basename = os.path.basename(fpath)
        relpath = os.path.relpath(fpath, root_path) if root_path else fpath
        relpath_normalized = relpath.replace("\\", "/")
        file_list_text += f"- {relpath_normalized}\n"
        file_map[basename] = fpath
        file_map[relpath_normalized] = fpath
        file_map[basename.lower()] = fpath
        file_map[relpath_normalized.lower()] = fpath

    if not file_list_text:
        file_list_text = "(未选择文件)"

    return file_list_text, file_map


def resolve_file(fname: str, file_map: dict) -> str:
    """
    从 file_map 中解析文件路径，使用五级匹配策略。

    Returns:
        绝对路径 或 None
    """
    fname_normalized = fname.replace("\\", "/")
    fpath = file_map.get(fname)
    if not fpath:
        fpath = file_map.get(fname_normalized)
    if not fpath:
        fpath = file_map.get(fname.lower())
    if not fpath:
        fpath = file_map.get(fname_normalized.lower())
    if not fpath:
        fname_base = os.path.basename(fname_normalized).lower()
        for key, val in file_map.items():
            if fname_base and fname_base in key.lower():
                fpath = val
                break
    if not fpath:
        for key, val in file_map.items():
            if len(fname_normalized) > 2 and key.lower() in fname_normalized.lower():
                fpath = val
                break
    return fpath


def read_files_for_task(task_files: list, file_map: dict, root_path: str = ""):
    """
    读取任务相关文件内容，返回拼接后的文本和已读取的路径集合。

    Returns:
        (file_contents_text, read_paths_set)
    """
    file_contents = ""
    read_paths = set()
    for fname in task_files:
        fpath = resolve_file(fname, file_map)
        if fpath:
            content = read_file_full(fpath)
            relpath = os.path.relpath(fpath, root_path) if root_path else fpath
            file_contents += f"\n### 文件: {relpath}\n```\n{content}\n```\n"
            read_paths.add(fpath)
        else:
            file_contents += f"\n### 文件: {fname}\n[文件未找到]\n"

    if not file_contents:
        file_contents = "(此任务无需读取文件，或文件未找到)"

    return file_contents, read_paths
