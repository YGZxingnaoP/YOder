"""
web_search 工具 - 联网搜索(requests方案)
"""
import requests
from typing import Dict, Any
from urllib.parse import quote_plus
from ..base import BaseTool


class WebSearchTool(BaseTool):
    """联网搜索工具"""
    
    name = "web_search"
    description = "通过搜索引擎搜索关键词,返回搜索结果列表。用于获取实时信息、新闻、技术文档等。"
    permission = "safe"
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数(默认10)"
            }
        },
        "required": ["query"]
    }
    
    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行联网搜索"""
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 10)
        
        if not query.strip():
            return "错误: 搜索关键词不能为空"
        
        try:
            # 使用DuckDuckGo的HTML版本(无需API Key)
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 简单解析HTML(不依赖BeautifulSoup)
            html = response.text
            
            results = []
            
            # 查找搜索结果
            result_blocks = html.split('class="result__a"')
            
            for i, block in enumerate(result_blocks[1:], 1):  # 跳过第一个(不是结果)
                if i > max_results:
                    break
                
                # 提取标题和链接
                if 'href="' in block:
                    title_start = block.find(">") + 1
                    title_end = block.find("</a>")
                    if title_start > 0 and title_end > title_start:
                        title = block[title_start:title_end].strip()
                        
                        # 提取链接
                        href_start = block.find('href="') + 6
                        href_end = block.find('"', href_start)
                        if href_start > 5 and href_end > href_start:
                            url = block[href_start:href_end]
                            
                            # 提取摘要
                            snippet = ""
                            if 'class="result__snippet"' in block:
                                snippet_start = block.find('class="result__snippet"')
                                snippet_text_start = block.find(">", snippet_start) + 1
                                snippet_text_end = block.find("</", snippet_text_start)
                                if snippet_text_start > 0 and snippet_text_end > snippet_text_start:
                                    snippet = block[snippet_text_start:snippet_text_end].strip()
                            
                            results.append({
                                "title": title,
                                "url": url,
                                "snippet": snippet
                            })
            
            if not results:
                return f"未找到相关结果\n查询: {query}"
            
            # 格式化输出
            output = f"搜索结果: {query}\n"
            output += f"找到 {len(results)} 个结果\n"
            output += "=" * 60 + "\n\n"
            
            for i, result in enumerate(results, 1):
                output += f"{i}. {result['title']}\n"
                output += f"   URL: {result['url']}\n"
                if result['snippet']:
                    output += f"   摘要: {result['snippet']}\n"
                output += "\n"
            
            return output
            
        except requests.exceptions.Timeout:
            return "错误: 搜索请求超时(10秒),请稍后重试"
        except requests.exceptions.ConnectionError:
            return "错误: 网络连接失败,请检查网络设置"
        except Exception as e:
            return f"搜索失败: {str(e)}"
