"""
files_reader/token_cal.py
根据文件字节数估算 token 数和字符数（粗略估算，仅用于界面显示）。
估算规则：
- token 数 ≈ 字节数 / 4 （英文为主时较准）
- 字符数 ≈ 字节数 / 3 （假设 UTF-8 中文约 3 字节）
如果文件无法读取，返回 0。
"""
import os

def calc_token_info(file_path: str):
    """
    返回 (token_count, char_count) 元组。
    """
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return 0, 0

    # 简单估算，不做高精度处理
    token_est = max(1, size // 4)
    char_est = max(1, size // 3)
    return token_est, char_est