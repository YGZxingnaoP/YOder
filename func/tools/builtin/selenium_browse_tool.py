"""
selenium_browse 工具 - 使用Edge浏览器分析网页(支持JavaScript渲染)
"""
import os
import time
from typing import Dict, Any
from ..base import BaseTool


class SeleniumBrowseTool(BaseTool):
    """Selenium网页浏览工具"""
    
    name = "selenium_browse"
    description = (
        "使用Edge浏览器访问网页并提取内容。支持JavaScript渲染的动态页面、单页应用(SPA)、"
        "需要滚动加载的内容。适用于web_browse无法获取完整内容的场景。"
    )
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要访问的网页URL"
            },
            "wait_seconds": {
                "type": "integer",
                "description": "等待页面加载的秒数(默认3秒,动态页面可设为5-10秒)"
            },
            "scroll_to_bottom": {
                "type": "boolean",
                "description": "是否滚动到页面底部以触发懒加载内容(默认false)"
            },
            "extract_mode": {
                "type": "string",
                "description": "内容提取模式: 'full'(完整HTML)、'text'(纯文本)、'article'(文章正文,默认)",
                "enum": ["full", "text", "article"]
            },
            "max_length": {
                "type": "integer",
                "description": "最大返回内容长度(默认15000字符)"
            }
        },
        "required": ["url"]
    }
    
    def __init__(self, project_root: str = ""):
        super().__init__(project_root)
        self.driver_path = self._find_webdriver()
    
    def _find_webdriver(self) -> str:
        """查找WebDriver路径"""
        # 1. 项目根目录
        project_driver = os.path.join(self.project_root, "msedgedriver.exe")
        if os.path.exists(project_driver):
            return project_driver
        
        # 2. 系统PATH
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            driver_in_path = os.path.join(path_dir, "msedgedriver.exe")
            if os.path.exists(driver_in_path):
                return driver_in_path
        
        return ""
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行Selenium网页浏览"""
        url = arguments.get("url", "")
        wait_seconds = arguments.get("wait_seconds", 3)
        scroll_to_bottom = arguments.get("scroll_to_bottom", False)
        extract_mode = arguments.get("extract_mode", "article")
        max_length = arguments.get("max_length", 15000)
        
        if not url.strip():
            return "错误: URL不能为空"
        
        if not url.startswith(("http://", "https://")):
            return "错误: URL必须以 http:// 或 https:// 开头"
        
        if not self.driver_path:
            return (
                "错误: 未找到 msedgedriver.exe\n"
                "解决方法:\n"
                "1. 下载与Edge版本匹配的WebDriver\n"
                "2. 将msedgedriver.exe放入项目根目录或系统PATH\n"
                "3. 使用edge_check工具检测浏览器环境"
            )
        
        try:
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.edge.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError:
            return (
                "错误: selenium未安装\n"
                "请运行: pip install selenium>=4.0"
            )
        
        # 配置浏览器选项
        options = Options()
        options.add_argument("--headless")  # 无头模式
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-images")  # 禁用图片加速加载
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # 启动浏览器
        try:
            service = Service(executable_path=self.driver_path)
            driver = webdriver.Edge(service=service, options=options)
            driver.set_page_load_timeout(30)
            driver.set_script_timeout(30)
            
        except Exception as e:
            return f"错误: 无法启动Edge浏览器 - {str(e)}"
        
        try:
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(wait_seconds)
            
            # 如果需要滚动到底部
            if scroll_to_bottom:
                self._scroll_to_bottom(driver)
                time.sleep(1)  # 等待懒加载内容
            
            # 提取内容
            if extract_mode == "full":
                content = driver.page_source
                content_type = "完整HTML"
                
            elif extract_mode == "text":
                body = driver.find_element(By.TAG_NAME, "body")
                content = body.text
                content_type = "纯文本"
                
            else:  # article模式(默认)
                content = self._extract_article_content(driver)
                content_type = "文章正文"
            
            # 获取页面标题
            title = driver.title
            
            # 截断过长内容
            original_length = len(content)
            if len(content) > max_length:
                content = content[:max_length]
                truncated = True
            else:
                truncated = False
            
            # 格式化输出
            output = f"网页内容(Selenium): {url}\n"
            output += f"页面标题: {title}\n"
            output += f"提取模式: {content_type}\n"
            output += f"提取长度: {len(content)} 字符"
            if truncated:
                output += f" (原长度: {original_length} 字符,已截断)"
            output += "\n" + "=" * 60 + "\n\n"
            output += content
            
            return output
            
        except Exception as e:
            return f"网页浏览失败: {str(e)}"
            
        finally:
            try:
                driver.quit()
            except:
                pass
    
    def _scroll_to_bottom(self, driver):
        """滚动到页面底部以触发懒加载"""
        scroll_pause_time = 1
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        for _ in range(3):  # 最多滚动3次
            # 滚动到底部
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # 计算新的页面高度
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    
    def _extract_article_content(self, driver):
        """提取文章正文内容(智能过滤广告、导航栏等)"""
        from selenium.webdriver.common.by import By
        
        # 尝试提取常见的文章容器
        article_selectors = [
            "article",
            "[role='main']",
            "main",
            ".post-content",
            ".article-content",
            ".entry-content",
            ".content",
            "#content",
            ".post",
            ".article"
        ]
        
        for selector in article_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    # 取第一个匹配的元素
                    content = elements[0].text
                    if len(content) > 200:  # 内容足够长,认为是正文
                        return content
            except:
                continue
        
        # 回退:提取body中所有文本
        body = driver.find_element(By.TAG_NAME, "body")
        
        # 移除常见无关元素
        try:
            driver.execute_script("""
                var elements = document.querySelectorAll('nav, header, footer, aside, .sidebar, .ad, .advertisement, .banner');
                elements.forEach(function(el) { el.remove(); });
            """)
        except:
            pass
        
        return body.text
