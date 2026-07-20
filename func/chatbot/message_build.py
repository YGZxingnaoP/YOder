import json
import os
import re
import base64
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RECORDS_DIR = os.path.join(BASE_DIR, "records")

def _ensure_records_dir():
    if not os.path.exists(RECORDS_DIR):
        os.makedirs(RECORDS_DIR)

def parse_error(error_message: str) -> str:
    if not error_message:
        return "未知错误"
    if re.search(r"(不支持.*上传|图片|文件|多模态|upload|image|file.*not supported)", error_message, re.I):
        return "当前模型不支持上传图片或文件，请切换模型或移除附件。\n原始错误: " + error_message
    return error_message

def _read_pdf(file_path: str) -> str:
    try:
        import fitz
        doc = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except ImportError:
        return f"[无法读取PDF: 缺少 PyMuPDF 依赖，请运行 pip install PyMuPDF]"
    except Exception as e:
        return f"[读取PDF失败: {os.path.basename(file_path)} - {e}]"

def _read_docx(file_path: str) -> str:
    try:
        import docx
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        return f"[无法读取Word: 缺少 python-docx 依赖，请运行 pip install python-docx]"
    except Exception as e:
        return f"[读取Word失败: {os.path.basename(file_path)} - {e}]"

def read_file_as_content(file_path: str) -> Optional[Dict]:
    try:
        file_size = os.path.getsize(file_path)
        if file_size > 10240 * 1024:
            return {"type": "text", "text": f"[文件过大 ({file_size//1024}KB)，已跳过读取: {os.path.basename(file_path)}]"}
        mime_type = _guess_mime(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        if mime_type and mime_type.startswith("image/"):
            with open(file_path, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")
            data_url = f"data:{mime_type};base64,{b64}"
            return {"type": "image_url", "image_url": {"url": data_url}}
        elif ext == ".pdf":
            text = _read_pdf(file_path)
            return {"type": "text", "text": text}
        elif ext in (".docx", ".doc"):
            text = _read_docx(file_path)
            return {"type": "text", "text": text}
        else:
            with open(file_path, "rb") as f:
                data = f.read()
            text = data.decode("utf-8", errors="replace")
            return {"type": "text", "text": text}
    except Exception as e:
        return {"type": "text", "text": f"[读取文件失败: {os.path.basename(file_path)} - {e}]"}

def _guess_mime(file_path: str) -> Optional[str]:
    ext = os.path.splitext(file_path)[1].lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mapping.get(ext, None)

def build_message_list(
    system_prompt: str,
    user_text: str,
    history: List[Dict],
    upload_files: Optional[List[str]] = None,
    root_path: Optional[str] = None
) -> Tuple[List[Dict], List[Dict]]:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    api_content = [{"type": "text", "text": user_text}]
    ui_content = [{"type": "text", "text": user_text}]
    if upload_files:
        for fpath in upload_files:
            if os.path.isfile(fpath):
                file_block = read_file_as_content(fpath)
                if file_block:
                    api_content.append(file_block)
                    if file_block["type"] == "text":
                        ui_content.append({
                            "type": "file_content",
                            "file_name": os.path.basename(fpath),
                            "file_path": os.path.relpath(fpath, root_path) if root_path else fpath,
                            "text": file_block["text"]
                        })
                    else:
                        ui_content.append(file_block)
            if root_path:
                try:
                    rel = os.path.relpath(fpath, root_path)
                    api_content.append({"type": "text", "text": f"[文件位置: {rel}]"})
                except ValueError:
                    pass
    messages.append({"role": "user", "content": api_content})
    return messages, ui_content

def create_record_folder() -> str:
    _ensure_records_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    base_name = f"record-{today}"
    folder_path = os.path.join(RECORDS_DIR, base_name)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        return base_name
    i = 1
    while True:
        new_name = f"{base_name}.{i}"
        new_path = os.path.join(RECORDS_DIR, new_name)
        if not os.path.exists(new_path):
            os.makedirs(new_path)
            return new_name
        i += 1

def save_conversation(folder_name: str, messages: List[Dict]):
    folder_path = os.path.join(RECORDS_DIR, folder_name)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    file_path = os.path.join(folder_path, "chat.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def load_conversation(folder_name: str) -> List[Dict]:
    file_path = os.path.join(RECORDS_DIR, folder_name, "chat.json")
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def rename_conversation(old_name: str, new_name: str) -> bool:
    old_path = os.path.join(RECORDS_DIR, old_name)
    new_path = os.path.join(RECORDS_DIR, new_name)
    if not os.path.exists(old_path) or os.path.exists(new_path):
        return False
    os.rename(old_path, new_path)
    return True

def delete_conversation(folder_name: str) -> bool:
    folder_path = os.path.join(RECORDS_DIR, folder_name)
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        try:
            shutil.rmtree(folder_path)
            return True
        except Exception:
            return False
    return False

def list_conversations() -> List[str]:
    _ensure_records_dir()
    items = os.listdir(RECORDS_DIR)
    folders = [d for d in items if os.path.isdir(os.path.join(RECORDS_DIR, d))]
    folders.sort(key=lambda l: os.path.getmtime(os.path.join(RECORDS_DIR, l)), reverse=True)
    return folders
