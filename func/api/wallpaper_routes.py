"""
壁纸管理路由（/api/wallpapers）
"""
import os
import time

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from func.api.config import BASE_DIR

router = APIRouter()

WALLPAPER_DIR = os.path.join(BASE_DIR, "wallpapers")


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
