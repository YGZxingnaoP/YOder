@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YOder Build Script

:: ==========================================
:: Configuration
:: ==========================================
set APP_NAME=YOder
set EMBEDDED_PYTHON_DIR=env
set USE_PIP_CACHE=YES

echo ==========================================
echo        YOder Build Script
echo ==========================================
echo.

:: 0. Check embedded Python
echo [0/5] Checking embedded Python...
set PYTHON_CMD=
if exist "%~dp0%EMBEDDED_PYTHON_DIR%\python.exe" (
    set "PYTHON_CMD=%~dp0%EMBEDDED_PYTHON_DIR%\python.exe"
    goto :python_found
)
echo [ERROR] python.exe not found in %EMBEDDED_PYTHON_DIR%
pause & exit /b 1

:python_found
for /f "tokens=*" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] %PYTHON_VERSION%

:: 1. Configure _pth and pip
echo [1/5] Configuring Python environment...
for %%I in ("%PYTHON_CMD%") do set "PY_DIR=%%~dpI"

:: Enable site-packages in _pth
"%PYTHON_CMD%" -c "import os, glob; py_dir = r'%PY_DIR%'.rstrip('\\'); pth_files = glob.glob(os.path.join(py_dir, '*._pth')); pth = pth_files[0] if pth_files else None; exit(0) if not pth else None; content = open(pth, 'r', encoding='utf-8').read(); content = content.replace('#import site', 'import site'); open(pth, 'w', encoding='utf-8').write(content); print('[OK] Updated _pth')"

:: Ensure Lib\site-packages in _pth
for %%f in ("%PY_DIR%*._pth") do (
    findstr /i /c:"Lib\site-packages" "%%f" >nul || echo Lib\site-packages>> "%%f"
)

:: Install pip if needed
"%PYTHON_CMD%" -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing pip...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
    if not exist "get-pip.py" (
        echo [ERROR] Failed to download get-pip.py
        pause & exit /b 1
    )
    "%PYTHON_CMD%" get-pip.py -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    del /q get-pip.py
)

:: 2. Install Python dependencies + PyInstaller
echo [2/5] Installing dependencies...
if %USE_PIP_CACHE%==YES (
    set PIP_CACHE_DIR=%~dp0\.pip_cache
    if not exist "!PIP_CACHE_DIR!" mkdir "!PIP_CACHE_DIR!"
    "%PYTHON_CMD%" -m pip config set global.cache-dir "!PIP_CACHE_DIR!" >nul 2>&1
)

"%PYTHON_CMD%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if exist requirements.txt (
    "%PYTHON_CMD%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --exists-action w
)
"%PYTHON_CMD%" -m pip install --upgrade pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
"%PYTHON_CMD%" -m pip install Pillow -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --exists-action w >nul 2>&1
echo [OK] Dependencies installed

:: 3. Build frontend
echo [3/5] Building frontend...
cd /d "%~dp0frontend"

:: Check Node.js
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] npm not found, skipping frontend build
    goto :frontend_done
)

call npm install --silent
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed
    pause & exit /b 1
)
echo [OK] Frontend built successfully

:frontend_done
cd /d "%~dp0"

:: 4. Create launcher script
echo [4/5] Preparing PyInstaller...
set DIST_DIR=%~dp0dist
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

:: Create launcher.py (pywebview embedded window, onefile-aware)
(
echo import sys
echo import os
echo import shutil
echo import threading
echo import time
echo.
echo if getattr^(sys, 'frozen', False^):
echo     BASE_DIR = os.path.dirname^(sys.executable^)
echo     BUNDLED_DIR = sys._MEIPASS
echo     for d in ['wallpapers', os.path.join^('frontend', 'dist'^)]:
echo         dst = os.path.join^(BASE_DIR, d^)
echo         src = os.path.join^(BUNDLED_DIR, d^)
echo         if not os.path.exists^(dst^) and os.path.exists^(src^):
echo             if os.path.isdir^(src^):
echo                 shutil.copytree^(src, dst^)
echo             else:
echo                 os.makedirs^(os.path.dirname^(dst^), exist_ok=True^)
echo                 shutil.copy2^(src, dst^)
echo else:
echo     BASE_DIR = os.path.dirname^(os.path.abspath^(__file__^)^)
echo.
echo sys.path.insert^(0, BASE_DIR^)
echo os.chdir^(BASE_DIR^)
echo.
echo import uvicorn
echo import webview
echo.
echo def start_server^(^):
echo     uvicorn.run^("func.api.main:app", host="127.0.0.1", port=8000, log_level="error"^)
echo.
echo server_thread = threading.Thread^(target=start_server, daemon=True^)
echo server_thread.start^(^)
echo time.sleep^(2^)
echo.
echo def on_loaded^(window^):
echo     window.evaluate_js^("document.documentElement.style.zoom = '0.9'"^)
echo.
echo try:
echo     webview.create_window^("YOder", "http://127.0.0.1:8000", width=1400, height=900^)
echo     webview.start^(func=on_loaded^)
echo except Exception as e:
echo     import traceback
echo     traceback.print_exc^(^)
echo     input^("Press Enter to exit..."^)
) > "%~dp0launcher.py"

:: Convert PNG icon to ICO format
if exist "%~dp0icon.png" (
    echo [INFO] Converting icon.png to icon.ico...
    "%PYTHON_CMD%" -c "from PIL import Image; img = Image.open(r'%~dp0icon.png'); img.save(r'%~dp0icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if exist "%~dp0icon.ico" (
        set "ICON_ARG=--icon "%~dp0icon.ico""
        echo [OK] icon.ico created
    ) else (
        echo [WARN] icon.ico conversion failed, building without icon
        set "ICON_ARG="
    )
) else (
    echo [WARN] icon.png not found, building without icon
    set "ICON_ARG="
)

:: 5. Run PyInstaller
echo [5/5] Building exe (this may take a few minutes)...

"%PYTHON_CMD%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --add-data "func;func" ^
    --add-data "wallpapers;wallpapers" ^
    --add-data "frontend\dist;frontend\dist" ^
    --collect-data trafilatura ^
    --hidden-import=uvicorn ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    --hidden-import=webview ^
    --hidden-import=webview.platforms.edgechromium ^
    --collect-submodules fastapi ^
    --collect-submodules starlette ^
    --collect-submodules pydantic ^
    --collect-submodules openai ^
    --hidden-import=fastapi ^
    --hidden-import=starlette ^
    --hidden-import=starlette.middleware ^
    --hidden-import=starlette.middleware.cors ^
    --hidden-import=starlette.responses ^
    --hidden-import=starlette.staticfiles ^
    --hidden-import=anyio ^
    --hidden-import=anyio._backends ^
    --hidden-import=anyio._backends._asyncio ^
    --hidden-import=h11 ^
    --hidden-import=httptools ^
    --hidden-import=websockets ^
    --hidden-import=openai ^
    --hidden-import=pydantic ^
    --hidden-import=pydantic.deprecated ^
    --hidden-import=requests ^
    --hidden-import=urllib3 ^
    --hidden-import=certifi ^
    --hidden-import=charset_normalizer ^
    --hidden-import=idna ^
    --hidden-import=trafilatura ^
    --hidden-import=selenium ^
    --hidden-import=selenium.webdriver ^
    --hidden-import=selenium.webdriver.edge ^
    --hidden-import=selenium.webdriver.edge.service ^
    --hidden-import=selenium.webdriver.edge.options ^
    --hidden-import=selenium.webdriver.common ^
    --hidden-import=selenium.webdriver.common.by ^
    --hidden-import=selenium.webdriver.common.keys ^
    --hidden-import=selenium.webdriver.support ^
    --hidden-import=selenium.webdriver.support.ui ^
    --hidden-import=selenium.webdriver.support.expected_conditions ^
    --hidden-import=fitz ^
    --hidden-import=docx ^
    --hidden-import=multipart ^
    --hidden-import=python_multipart ^
    --hidden-import=typing_extensions ^
    --hidden-import=annotated_types ^
    --hidden-import=sniffio ^
    --hidden-import=httpcore ^
    --hidden-import=httpx ^
    --hidden-import=jinja2 ^
    --hidden-import=markupsafe ^
    --hidden-import=yaml ^
    --hidden-import=markdown ^
    --hidden-import=pygments ^
    --exclude-module=PySide6 ^
    --exclude-module=PySide6.QtCore ^
    --exclude-module=PySide6.QtGui ^
    --exclude-module=PySide6.QtWidgets ^
    --exclude-module=shiboken6 ^
    --exclude-module=PIL ^
    --exclude-module=setuptools ^
    --exclude-module=wheel ^
    --exclude-module=test ^
    --exclude-module=tests ^
    --log-level WARN ^
    --distpath "%~dp0dist" ^
    --workpath "%~dp0build" ^
    !ICON_ARG! ^
    "%~dp0launcher.py" > build.log 2>&1

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller failed. Check build.log for details.
    type build.log | findstr /i "error"
    pause & exit /b 1
)

:: Clean up launcher.py
del /q "%~dp0launcher.py"

:: Copy non-sensitive config files next to exe (skip info.json which contains API keys)
if not exist "%DIST_DIR%\config" mkdir "%DIST_DIR%\config"
for %%f in (tools.json last_conv.json) do (
    if exist "%~dp0config\%%f" copy /Y "%~dp0config\%%f" "%DIST_DIR%\config\%%f" >nul
)
:: wallpapers (including status.json) already bundled and copied by launcher on first run
:: Also copy wallpapers next to exe for immediate availability
if exist "%~dp0wallpapers" (
    xcopy /E /I /Q "%~dp0wallpapers" "%DIST_DIR%\wallpapers" >nul
)

:: Create start.bat
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo start "" "%APP_NAME%.exe"
) > "%DIST_DIR%\start.bat"

:: Clean build artifacts
if exist "%~dp0build" rmdir /s /q "%~dp0build"
if exist "%~dp0%APP_NAME%.spec" del /q "%~dp0%APP_NAME%.spec"
if exist "%~dp0icon.ico" del /q "%~dp0icon.ico"

echo.
echo ==========================================
echo        Build Complete!
echo ==========================================
echo.
echo   Output:  dist\
echo   Exe:     dist\%APP_NAME%.exe
echo   Start:   dist\start.bat
echo.
pause
