"""
浏览器检测路由（/api/browser）
"""
import os
import subprocess

from fastapi import APIRouter

from func.api.config import BASE_DIR

router = APIRouter()


@router.get("/api/browser/detect")
async def detect_browser(browser: str = "edge"):
    """检测浏览器版本和WebDriver状态"""
    browser = browser.lower()
    result = {
        "browser": browser,
        "installed": False,
        "version": "",
        "path": "",
        "webdriver_installed": False,
        "webdriver_version": "",
        "webdriver_download_url": "",
        "webdriver_official_url": "",
        "install_url": ""
    }

    if browser == "edge":
        result["install_url"] = "https://www.microsoft.com/edge"
        result["webdriver_official_url"] = "https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/"

        # 检测Edge版本
        if os.name == "nt":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Edge\BLBeacon")
                version, _ = winreg.QueryValueEx(key, "version")
                winreg.CloseKey(key)
                result["installed"] = True
                result["version"] = version
                result["path"] = "Edge"
            except Exception:
                # 回退: 文件系统检测
                edge_paths = [
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
                ]
                for p in edge_paths:
                    if os.path.exists(p):
                        result["installed"] = True
                        result["path"] = p
                        try:
                            info = subprocess.STARTUPINFO()
                            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                            info.wShowWindow = subprocess.SW_HIDE
                            out = subprocess.check_output(
                                ["powershell", "-Command", f"(Get-Item '{p}').VersionInfo.FileVersion"],
                                startupinfo=info, text=True, timeout=5
                            )
                            result["version"] = out.strip()
                        except Exception:
                            result["version"] = "未知版本"
                        break

        # 检测Edge WebDriver (msedgedriver.exe)
        if result["installed"]:
            # 检查PATH和项目目录中的msedgedriver
            webdriver_names = ["msedgedriver.exe"]
            for wd_name in webdriver_names:
                # 检查系统PATH
                for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                    if os.path.exists(os.path.join(path_dir, wd_name)):
                        result["webdriver_installed"] = True
                        result["webdriver_version"] = result["version"]
                        break
                # 检查项目根目录
                if os.path.exists(os.path.join(BASE_DIR, wd_name)):
                    result["webdriver_installed"] = True
                    result["webdriver_version"] = result["version"]
                    break

            # 生成匹配版本下载链接
            if result["version"]:
                try:
                    major = int(result["version"].split('.')[0])
                    if major >= 115:
                        result["webdriver_download_url"] = f"https://msedgedriver.microsoft.com/{result['version']}/edgedriver_win64.zip"
                except Exception:
                    pass

    elif browser == "chrome":
        result["install_url"] = "https://www.google.com/chrome/"
        result["webdriver_official_url"] = "https://chromedriver.chromium.org/downloads"

        if os.name == "nt":
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
            ]
            for p in chrome_paths:
                if os.path.exists(p):
                    result["installed"] = True
                    result["path"] = p
                    try:
                        info = subprocess.STARTUPINFO()
                        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        info.wShowWindow = subprocess.SW_HIDE
                        out = subprocess.check_output(
                            ["powershell", "-Command", f"(Get-Item '{p}').VersionInfo.FileVersion"],
                            startupinfo=info, text=True, timeout=5
                        )
                        result["version"] = out.strip()
                    except Exception:
                        result["version"] = "未知版本"
                    break

            # 检测Chrome WebDriver
            if result["installed"]:
                for wd_name in ["chromedriver.exe"]:
                    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                        if os.path.exists(os.path.join(path_dir, wd_name)):
                            result["webdriver_installed"] = True
                            break
                    if os.path.exists(os.path.join(BASE_DIR, wd_name)):
                        result["webdriver_installed"] = True
                        break

                if result["version"]:
                    try:
                        major = int(result["version"].split('.')[0])
                        if major >= 115:
                            result["webdriver_download_url"] = f"https://storage.googleapis.com/chrome-for-testing-public/{result['version']}/win64/chromedriver-win64.zip"
                        result["webdriver_official_url"] = "https://googlechromelabs.github.io/chrome-for-testing/"
                    except Exception:
                        pass

    elif browser == "firefox":
        result["install_url"] = "https://www.mozilla.org/firefox/new/"
        result["webdriver_official_url"] = "https://github.com/mozilla/geckodriver/releases"

        if os.name == "nt":
            ff_paths = [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
            ]
            for p in ff_paths:
                if os.path.exists(p):
                    result["installed"] = True
                    result["path"] = p
                    try:
                        info = subprocess.STARTUPINFO()
                        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        info.wShowWindow = subprocess.SW_HIDE
                        out = subprocess.check_output(
                            ["powershell", "-Command", f"(Get-Item '{p}').VersionInfo.FileVersion"],
                            startupinfo=info, text=True, timeout=5
                        )
                        result["version"] = out.strip()
                    except Exception:
                        result["version"] = "未知版本"
                    break

            if result["installed"]:
                for wd_name in ["geckodriver.exe"]:
                    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                        if os.path.exists(os.path.join(path_dir, wd_name)):
                            result["webdriver_installed"] = True
                            break
                    if os.path.exists(os.path.join(BASE_DIR, wd_name)):
                        result["webdriver_installed"] = True
                        break

    return result
