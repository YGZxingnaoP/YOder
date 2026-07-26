@echo off
setlocal EnableDelayedExpansion
:: 设置控制台为 UTF-8 编码，防止中文路径乱码
chcp 65001 >nul
title 项目打包与环境配置工具

:: ==========================================
:: 配置区
:: ==========================================
set ENTRY_FILE=run.py
set APP_NAME=YOder
set ICON_FILE=icon.ico
set ICON_SOURCE=icon.png
set EMBEDDED_PYTHON_DIR=env
set USE_PIP_CACHE=YES
set INCREMENTAL_BUILD=YES

echo ==========================================
echo        开始环境检测与初始化
echo ==========================================

:: 0. 检查是否需要重新配置环境
echo [0/6] 检查环境配置状态...
set NEED_RECONFIG=NO
for %%I in ("%~dp0%EMBEDDED_PYTHON_DIR%") do set "PY_DIR=%%~dpI"
if exist "%PY_DIR%*._pth" (
    findstr /c:"import site" "%PY_DIR%*._pth" >nul
    if !errorlevel! neq 0 set NEED_RECONFIG=YES
) else (
    set NEED_RECONFIG=YES
)
if not exist "%PY_DIR%pip" set NEED_RECONFIG=YES
if !NEED_RECONFIG! == NO (
    echo [跳过] 环境已配置，跳过初始化步骤
) else (
    echo [提示] 需要重新配置环境
)

:: 1. 检测内嵌 Python 环境
echo [1/6] 正在检测内嵌 Python 环境...
set PYTHON_CMD=
if exist "%~dp0%EMBEDDED_PYTHON_DIR%\python.exe" (
    set "PYTHON_CMD=%~dp0%EMBEDDED_PYTHON_DIR%\python.exe"
    goto :python_found
)
if exist "%~dp0python.exe" (
    set "PYTHON_CMD=%~dp0python.exe"
    goto :python_found
)

echo [错误] 未找到 python.exe！
pause & exit /b 1

:python_found
for /f "tokens=*" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [成功] 检测到 %PYTHON_VERSION%  路径: %PYTHON_CMD%

:: 2. 安全配置 _pth 文件
if !NEED_RECONFIG! == YES goto :reconfig_env
goto :skip_reconfig

:reconfig_env
echo [2/6] 正在安全配置内嵌 Python 路径...
for %%I in ("%PYTHON_CMD%") do set "PY_DIR=%%~dpI"

"%PYTHON_CMD%" -c "import os, glob; pth_files = glob.glob(os.path.join(r'%PY_DIR%', '*._pth')); pth = pth_files[0] if pth_files else None; exit(0) if not pth else None; content = open(pth, 'r', encoding='utf-8').read(); content = content.replace('#import site', 'import site'); open(pth, 'w', encoding='utf-8').write(content); print(f'[成功] 已在 {os.path.basename(pth)} 中启用 import site')"

for %%f in ("%PY_DIR%*._pth") do (
    findstr /i /c:"Lib\site-packages" "%%f" >nul || echo Lib\site-packages>> "%%f"
)

:skip_reconfig

:: 3. 初始化 pip 环境
if !NEED_RECONFIG! == YES goto :init_pip
goto :skip_pip

:init_pip
echo [3/6] 正在检测并初始化 pip...
"%PYTHON_CMD%" -m pip --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [信息] 未检测到 pip，正在下载 get-pip.py...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
    if not exist "get-pip.py" (
        echo [错误] 下载 get-pip.py 失败！
        pause & exit /b 1
    )
    "%PYTHON_CMD%" get-pip.py -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    del /q get-pip.py
    echo [成功] pip 初始化完成。
) else (
    echo [成功] 检测到 pip 环境。
)

:skip_pip

:: 4. 安装项目依赖与 PyInstaller
echo [4/6] 正在安装项目依赖与 PyInstaller...
if !USE_PIP_CACHE! == YES (
    set PIP_CACHE_DIR=%~dp0\.pip_cache
    if not exist "!PIP_CACHE_DIR!" mkdir "!PIP_CACHE_DIR!"
    "%PYTHON_CMD%" -m pip config set global.cache-dir "!PIP_CACHE_DIR!" >nul 2>&1
)

"%PYTHON_CMD%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if exist requirements.txt (
    "%PYTHON_CMD%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --exists-action w
)
"%PYTHON_CMD%" -m pip install --upgrade pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1

echo [验证] 检查关键依赖...
"%PYTHON_CMD%" -c "import PySide6; print('[OK] PySide6:', PySide6.__version__)" 2>nul || echo [警告] PySide6 未安装
"%PYTHON_CMD%" -c "import fitz; print('[OK] fitz ready')" 2>nul || echo [警告] fitz 未安装

echo [成功] 依赖与打包工具准备就绪。

echo ==========================================
echo        环境准备完成，开始核心打包...
echo ==========================================

:: 5. PyInstaller 核心打包
echo [打包中] 正在执行 PyInstaller，请勿关闭窗口...

if /I "%INCREMENTAL_BUILD%"=="NO" (
    if exist build rmdir /s /q build
    if exist dist rmdir /s /q dist
    if exist *.spec del /q *.spec
)
if exist build.log del /q build.log

echo [提示] 开始打包，预计需要 2-5 分钟...
timeout /t 2 /nobreak >nul

:: 自动生成 .ico 图标
set ICON_ARG=
if exist "%ICON_SOURCE%" (
    if not exist "%ICON_FILE%" (
        echo [信息] 正在将 %ICON_SOURCE% 转换为 %ICON_FILE%...
        "%PYTHON_CMD%" -c "from PIL import Image; img = Image.open(r'%ICON_SOURCE%'); img.save(r'%ICON_FILE%', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
        if !errorlevel! neq 0 (
            echo [警告] 图标转换失败，将使用默认图标
        ) else (
            set "ICON_ARG=--icon=%ICON_FILE%"
        )
    ) else (
        set "ICON_ARG=--icon=%ICON_FILE%"
    )
)

"%PYTHON_CMD%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" !ICON_ARG! ^
    --add-data "func/ui;func/ui" ^
    --add-data "%ICON_SOURCE%;." ^
    --collect-all PySide6.QtWebEngineWidgets ^
    --collect-all PySide6.QtWebEngineCore ^
    --hidden-import=fitz ^
    --log-level WARN ^
    "%ENTRY_FILE%" > build.log 2>&1

echo [完成] PyInstaller 执行完毕，退出码: !errorlevel!

:: 6. 异常处理与产物验证
if !errorlevel! neq 0 (
    echo [错误] 打包失败！请查看 build.log
    more /e /tail:10 build.log
    pause & exit /b 1
)

set EXE_PATH=dist\%APP_NAME%.exe
if not exist "%EXE_PATH%" (
    echo [错误] 未在 dist 目录找到 %APP_NAME%.exe
    pause & exit /b 1
)

echo ==========================================
echo        打包成功！
echo ==========================================
echo [产物路径] %~dp0%EXE_PATH%
dir /-c "%EXE_PATH%" | findstr /C:"%APP_NAME%.exe"

:: 7. 临时文件清理
if /I "%INCREMENTAL_BUILD%"=="NO" (
    if exist build rmdir /s /q build
    if exist *.spec del /q *.spec
    echo [清理] 临时文件清理完毕
) else (
    echo [提示] 增量打包模式，保留了build目录
)

echo.
echo ==========================================
echo 打包完成！
echo ==========================================
echo   1. 测试 dist\%APP_NAME%.exe
echo   2. 可将 dist 文件夹分发给其他用户
echo   3. 重新打包直接运行 build.bat
echo.
pause
