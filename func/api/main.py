"""
YOder FastAPI后端服务 - 入口文件
替代原有Flask架构,支持Tool Calls和流式响应

路由已拆分到各独立模块，本文件仅负责：
  - 创建 FastAPI app
  - 挂载静态资源 / CORS
  - 注册启动事件
  - 包含所有路由模块
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from func.api.config import BASE_DIR, FRONTEND_DIR
from func.api.startup import init_tools

# ── 路由模块 ──────────────────────────────────
from func.api.config_routes   import router as config_router
from func.api.chat_routes     import router as chat_router
from func.api.chat_mgmt      import router as chat_mgmt_router
from func.api.memory_routes   import router as memory_router
from func.api.tools_routes    import router as tools_router
from func.api.browser_routes  import router as browser_router
from func.api.wallpaper_routes import router as wallpaper_router

# ── 创建 App ──────────────────────────────────
app = FastAPI(title="YOder API", version="2.0.0")

# 静态文件 - 挂载前端构建产物
if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 启动事件 ──────────────────────────────────
@app.on_event("startup")
async def startup_event():
    init_tools()

# ── 注册路由模块 ──────────────────────────────
app.include_router(config_router)
app.include_router(chat_router)
app.include_router(chat_mgmt_router)
app.include_router(memory_router)
app.include_router(tools_router)
app.include_router(browser_router)
app.include_router(wallpaper_router)


# ── 前端入口 ──────────────────────────────────
@app.get("/")
async def serve_frontend():
    """Serve frontend index.html"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "YOder API is running. Frontend not built yet."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
