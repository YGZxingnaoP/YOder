@echo off
:: 设置控制台为 UTF-8 编码，防止中文路径乱码
chcp 65001 >nul
title 项目打包与环境配置工具 (Embedded Python 版)

:: ==========================================
:: 配置区 (可根据实际情况修改)
:: ==========================================
set ENTRY_FILE=run.py
set APP_NAME=YOder
set ICON_FILE=icon.png
:: 【关键】内嵌 Python 所在的相对目录（请根据实际解压路径修改，如 env, python 等）
set EMBEDDED_PYTHON_DIR=env

echo ==========================================
echo        开始环境检测与初始化 (Embedded)
echo ==========================================

:: 1. 检测内嵌 Python 环境 (优先检测本地目录，拒绝依赖系统全局环境变量)
echo [1/5] 正在检测内嵌 Python 环境...
set PYTHON_CMD=
if exist "%~dp0%EMBEDDED_PYTHON_DIR%\python.exe" (
    set "PYTHON_CMD=%~dp0%EMBEDDED_PYTHON_DIR%\python.exe"
    goto :python_found
)
if exist "%~dp0python.exe" (
    set "PYTHON_CMD=%~dp0python.exe"
    goto :python_found
)

echo [错误] 未在当前目录或 %EMBEDDED_PYTHON_DIR% 目录下找到 python.exe！
echo [提示] 请确保已下载 Python Embedded (内嵌版) 并解压到正确目录。
pause & exit /b 1

:python_found
for /f "tokens=*" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [成功] 检测到 %PYTHON_VERSION% (路径: %PYTHON_CMD%)

:: 2. 安全配置 _pth 文件 (使用内嵌 Python 自身修改，避免 PowerShell 引入 BOM 编码问题)
echo [2/5] 正在安全配置内嵌 Python 路径 (_pth)...
for %%I in ("%PYTHON_CMD%") do set "PY_DIR=%%~dpI"

:: 使用内嵌 Python 执行单行脚本修改 _pth，取消 #import site 注释
"%PYTHON_CMD%" -c ^
"import os, glob; ^
pth_files = glob.glob(os.path.join(r'%PY_DIR%', '*._pth')); ^
pth = pth_files[0] if pth_files else None; ^
exit(0) if not pth else None; ^
content = open(pth, 'r', encoding='utf-8').read(); ^
content = content.replace('#import site', 'import site'); ^
open(pth, 'w', encoding='utf-8').write(content); ^
print(f'[成功] 已在 {os.path.basename(pth)} 中启用 import site')"

:: 追加 Lib\site-packages 到搜索路径 (使用 findstr 防止重复追加)
for %%f in ("%PY_DIR%*._pth") do (
    findstr /i /c:"Lib\site-packages" "%%f" >nul || echo Lib\site-packages>> "%%f"
)

:: 3. 初始化 pip 环境 (Embedded 默认无 pip，需手动引导)
echo [3/5] 正在检测并初始化 pip...
"%PYTHON_CMD%" -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 未检测到 pip，正在下载 get-pip.py...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
    if not exist "get-pip.py" (
        echo [错误] 下载 get-pip.py 失败！请检查网络连接。
        pause & exit /b 1
    )
    echo [信息] 正在安装 pip，请稍候...
    "%PYTHON_CMD%" get-pip.py -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    del /q get-pip.py
    echo [成功] pip 初始化完成。
) else (
    echo [成功] 检测到 pip 环境。
)

:: 4. 安装项目依赖与 PyInstaller
echo [4/5] 正在安装项目依赖与 PyInstaller...
"%PYTHON_CMD%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if exist requirements.txt (
    "%PYTHON_CMD%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)
"%PYTHON_CMD%" -m pip install --upgrade pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo [成功] 依赖与打包工具准备就绪。

echo ==========================================
echo        环境准备完成，开始核心打包...
echo ==========================================

:: 5. PyInstaller 核心打包
echo [打包中] 正在执行 PyInstaller，耗时较长，请勿关闭窗口...
if exist build.log del /q build.log

"%PYTHON_CMD%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --name "%APP_NAME%" ^
    --icon="%ICON_FILE%" ^
    --add-data "func/ui;func/ui" ^
    --add-data "%ICON_FILE%;." ^
    --collect-all PySide6.QtWebEngineWidgets ^
    --collect-all PySide6.QtWebEngineCore ^
    --hidden-import=fitz ^
    "%ENTRY_FILE%" > build.log 2>&1

:: 6. 异常处理与产物验证
if %errorlevel% neq 0 (
    echo [错误] 打包失败！请查看根目录下的 build.log 排查错误。
    pause & exit /b 1
)

set EXE_PATH=dist\%APP_NAME%.exe
if not exist "%EXE_PATH%" (
    echo [错误] 未在 dist 目录找到 %APP_NAME%.exe！
    pause & exit /b 1
)

echo ==========================================
echo        打包成功！
echo ==========================================
echo [产物路径] %~dp0%EXE_PATH%

:: 7. 临时文件清理
if exist build rmdir /s /q build
if exist *.spec del /q *.spec
echo [清理] 临时文件清理完毕。
pause
