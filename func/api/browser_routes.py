"""
浏览器检测路由（/api/browser）
"""
import os
import re
import subprocess
import sys

from fastapi import APIRouter

from func.api.config import BASE_DIR

router = APIRouter()


def _find_driver(driver_name: str) -> str:
    """查找 driver 可执行文件，返回完整路径或空字符串。
    exe 模式：只查 exe 同级目录（用户需自行放置）
    dev 模式：查项目目录 + 系统 PATH
    """
    is_frozen = getattr(sys, 'frozen', False)

    # exe 模式：只查 exe 同级目录
    if is_frozen:
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, driver_name)
        return p if os.path.exists(p) else ""

    # dev 模式：查项目目录
    p = os.path.join(BASE_DIR, driver_name)
    if os.path.exists(p):
        return p
    # dev 模式：查系统 PATH
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(path_dir, driver_name)
        if os.path.exists(p):
            return p
    return ""


def _get_driver_version(driver_path: str) -> str:
    """通过 --version 获取 driver 版本号"""
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        out = subprocess.check_output(
            [driver_path, "--version"],
            startupinfo=info, text=True, timeout=5
        )
        m = re.search(r'(\d+\.\d+[\.\d]*)', out)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _major(version_str: str) -> int:
    """提取版本号主版本，失败返回 0"""
    try:
        return int(version_str.split('.')[0])
    except Exception:
        return 0


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

        # 检测Edge版本（同时查 HKLM 和 HKCU）
        if os.name == "nt":
            import winreg
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Edge\BLBeacon")
                    version, _ = winreg.QueryValueEx(key, "version")
                    winreg.CloseKey(key)
                    result["installed"] = True
                    result["version"] = version
                    result["path"] = "Edge"
                    break
                except Exception:
                    pass

            if not result["installed"]:
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

        # 检测Edge WebDriver
        if result["installed"]:
            driver_path = _find_driver("msedgedriver.exe")
            if driver_path:
                wd_ver = _get_driver_version(driver_path)
                result["webdriver_version"] = wd_ver or "未知"
                # 只有 major 版本匹配才视为已安装
                if wd_ver and _major(wd_ver) == _major(result["version"]):
                    result["webdriver_installed"] = True

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
                driver_path = _find_driver("chromedriver.exe")
                if driver_path:
                    wd_ver = _get_driver_version(driver_path)
                    result["webdriver_version"] = wd_ver or "未知"
                    if wd_ver and _major(wd_ver) == _major(result["version"]):
                        result["webdriver_installed"] = True

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
                driver_path = _find_driver("geckodriver.exe")
                if driver_path:
                    wd_ver = _get_driver_version(driver_path)
                    result["webdriver_version"] = wd_ver or "未知"
                    # geckodriver 版本独立于 Firefox，找到即视为已安装
                    result["webdriver_installed"] = True

    return result
