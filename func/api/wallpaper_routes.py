"""
壁纸管理路由（/api/wallpapers）
"""
import json
import os
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from func.api.config import BASE_DIR

router = APIRouter()

WALLPAPER_DIR = os.path.join(BASE_DIR, "wallpapers")
STATUS_PATH = os.path.join(WALLPAPER_DIR, "status.json")


@router.get("/api/wallpapers")
async def list_wallpapers():
    """获取已保存的壁纸列表"""
    os.makedirs(WALLPAPER_DIR, exist_ok=True)
    wallpapers = []
    for f in sorted(os.listdir(WALLPAPER_DIR)):
        ext = f.rsplit('.', 1)[-1].lower() if '.' in f else ''
        if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'):
            filepath = os.path.join(WALLPAPER_DIR, f)
            wallpapers.append({
                "filename": f,
                "url": f"/api/wallpapers/{f}",
                "size": os.path.getsize(filepath)
            })
    return wallpapers


@router.post("/api/wallpapers/upload")
async def upload_wallpaper(file: UploadFile = File(...)):
    """上传壁纸图片并保存到wallpapers文件夹"""
    os.makedirs(WALLPAPER_DIR, exist_ok=True)

    # 生成唯一文件名
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
    timestamp = int(time.time())
    saved_name = f"wp_{timestamp}.{ext}"
    saved_path = os.path.join(WALLPAPER_DIR, saved_name)

    # 保存文件
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "filename": saved_name,
        "url": f"/api/wallpapers/{saved_name}"
    }


@router.get("/api/wallpapers/status")
async def get_wallpaper_status():
    """读取壁纸状态（从 wallpapers/status.json）"""
    if not os.path.exists(STATUS_PATH):
        return {}
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@router.post("/api/wallpapers/status")
async def save_wallpaper_status(request: Request):
    """保存壁纸状态到 wallpapers/status.json"""
    os.makedirs(WALLPAPER_DIR, exist_ok=True)
    data = await request.json()
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "success"}


@router.get("/api/wallpapers/{filename}")
async def serve_wallpaper(filename: str):
    """提供壁纸图片文件"""
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="壁纸不存在")

    # 安全检查: 防止路径穿越
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="无效文件名")

    return FileResponse(filepath)
