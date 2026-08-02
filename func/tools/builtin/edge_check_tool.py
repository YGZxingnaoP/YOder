"""
edge_check 工具 - 检测Edge浏览器版本并提供WebDriver下载链接
"""
import os
import subprocess
import re
from typing import Dict, Any
from ..base import BaseTool


class EdgeCheckTool(BaseTool):
    """Edge浏览器版本检测工具"""
    
    name = "edge_check"
    description = "检测Microsoft Edge浏览器是否安装及版本号,并提供对应WebDriver的下载地址。用于Selenium浏览器模式的环境检查。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行Edge版本检测"""
        
        # 1. 检测Edge是否安装
        edge_info = self._detect_edge()
        
        if not edge_info["installed"]:
            output = "Edge浏览器未检测到\n\n"
            output += "请安装Microsoft Edge:\n"
            output += "下载地址: https://www.microsoft.com/edge\n\n"
            output += "注意: Selenium浏览器模式需要Edge浏览器支持"
            return output
        
        # 2. 格式化输出
        output = f"Edge浏览器检测结果\n"
        output += "=" * 60 + "\n\n"
        output += f"状态: 已安装\n"
        output += f"版本: {edge_info['version']}\n"
        output += f"路径: {edge_info['path']}\n\n"
        
        # 3. 提取主版本号
        try:
            major_version = int(edge_info['version'].split('.')[0])
        except:
            major_version = 0
        
        # 4. 提供WebDriver下载链接
        output += "WebDriver下载:\n"
        output += "-" * 60 + "\n"
        
        if major_version >= 115:
            # 新版本使用Edge WebDriver
            download_url = f"https://msedgedriver.microsoft.com/{edge_info['version']}/edgedriver_win64.zip"
            output += f"推荐下载 (匹配版本 {edge_info['version']}):\n"
            output += f"{download_url}\n\n"
            
            output += "其他版本:\n"
            output += f"https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/\n\n"
        else:
            # 旧版本
            output += "请访问官方下载页面:\n"
            output += "https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/\n\n"
        
        # 5. 使用说明
        output += "使用说明:\n"
        output += "-" * 60 + "\n"
        output += "1. 下载与Edge版本匹配的WebDriver\n"
        output += "2. 解压后将 msedgedriver.exe 放入项目目录或系统PATH\n"
        output += "3. 在UI中开启'浏览器模式'即可使用Selenium功能\n\n"
        
        output += "注意事项:\n"
        output += "- WebDriver版本必须与Edge浏览器版本匹配\n"
        output += "- Edge自动更新可能导致版本不匹配,需重新下载WebDriver\n"
        output += "- 建议关闭Edge自动更新以避免频繁更新WebDriver"
        
        return output
    
    def _detect_edge(self) -> Dict[str, Any]:
        """检测Edge浏览器安装信息"""
        result = {
            "installed": False,
            "version": "",
            "path": ""
        }
        
        # Windows平台检测
        if os.name == "nt":
            # 方法1: 通过注册表检测
            try:
                import winreg
                key_path = r"SOFTWARE\Microsoft\Edge\BLBeacon"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
                version, _ = winreg.QueryValueEx(key, "version")
                winreg.CloseKey(key)
                
                result["installed"] = True
                result["version"] = version
                result["path"] = "注册表检测"
                return result
            except:
                pass
            
            # 方法2: 通过文件系统检测
            edge_paths = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
            ]
            
            for path in edge_paths:
                if os.path.exists(path):
                    result["installed"] = True
                    result["path"] = path
                    
                    # 尝试获取文件版本
                    try:
                        info = subprocess.STARTUPINFO()
                        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        info.wShowWindow = subprocess.SW_HIDE
                        
                        output = subprocess.check_output(
                            ["powershell", "-Command", 
                             f"(Get-Item '{path}').VersionInfo.FileVersion"],
                            startupinfo=info,
                            text=True,
                            timeout=5
                        )
                        result["version"] = output.strip()
                    except:
                        result["version"] = "未知版本"
                    
                    return result
        
        # 其他平台(Linux/Mac)
        else:
            try:
                output = subprocess.check_output(
                    ["microsoft-edge", "--version"],
                    text=True,
                    timeout=5
                )
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output)
                if match:
                    result["installed"] = True
                    result["version"] = match.group(1)
                    result["path"] = "microsoft-edge"
            except:
                pass
        
        return result
