"""
web_browse 工具 - 网页内容提取(requests+trafilatura方案)
"""
import requests
from typing import Dict, Any
from ..base import BaseTool


class WebBrowseTool(BaseTool):
    """网页浏览工具"""
    
    name = "web_browse"
    description = "访问指定URL并提取网页正文内容。用于深度阅读和分析网页内容,自动过滤广告和无关元素。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要访问的网页URL"
            },
            "max_length": {
                "type": "integer",
                "description": "最大返回内容长度(默认8000字符)"
            }
        },
        "required": ["url"]
    }
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行网页浏览"""
        url = arguments.get("url", "")
        max_length = arguments.get("max_length", 8000)
        
        if not url.strip():
            return "错误: URL不能为空"
        
        # URL格式验证
        if not url.startswith(("http://", "https://")):
            return "错误: URL必须以 http:// 或 https:// 开头"
        
        try:
            # 1. 获取网页内容
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
            }
            
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return f"错误: URL返回的不是HTML页面 (Content-Type: {content_type})"
            
            html = response.text
            
            # 2. 使用trafilatura提取正文(如果可用)
            try:
                import trafilatura
                content = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=True,
                    include_images=False,
                    include_links=False,
                    include_formatting=False
                )
                
                if not content:
                    # 回退到简单提取
                    content = self._simple_extract(html)
                    
            except ImportError:
                # trafilatura未安装,使用简单提取
                content = self._simple_extract(html)
            
            if not content:
                return "错误: 无法提取网页内容"
            
            # 3. 截断过长内容
            if len(content) > max_length:
                content = content[:max_length] + f"\n\n...(内容已截断,原长度: {len(content)} 字符)"
            
            # 4. 格式化输出
            output = f"网页内容: {url}\n"
            output += f"提取长度: {len(content)} 字符\n"
            output += "=" * 60 + "\n\n"
            output += content
            
            return output
            
        except requests.exceptions.Timeout:
            return "错误: 网页加载超时(15秒),请稍后重试"
        except requests.exceptions.ConnectionError:
            return "错误: 无法连接到服务器,请检查网络或URL是否正确"
        except requests.exceptions.HTTPError as e:
            return f"错误: HTTP错误 - {e.response.status_code} {e.response.reason}"
        except Exception as e:
            return f"网页浏览失败: {str(e)}"
    
    def _simple_extract(self, html: str) -> str:
        """简单HTML提取(trafilatura不可用时的回退方案)"""
        import re
        
        # 移除script和style标签
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # 清理空白字符
        text = re.sub(r'\s+', ' ', text)
        text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        
        return text
