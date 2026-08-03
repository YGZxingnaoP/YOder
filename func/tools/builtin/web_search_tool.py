"""
web_search 工具 - 联网搜索（Bing CN 方案）

基于 cn.bing.com 的 HTML 搜索结果解析，国内可无障碍访问。
不依赖任何第三方库，纯 requests + 字符串解析。

原始 DuckDuckGo 版本位于: func/tools/builtin/web_search_tool.py（未修改）
本文件为 Bing CN 替代方案，可直接替换使用。
"""
import re
import requests
from typing import Dict, Any
from urllib.parse import quote_plus
from html import unescape as html_unescape

# 如果放到 func/tools/builtin/ 内使用，请改为:
# from ..base import BaseTool
# 这里保持独立可运行
try:
    from func.tools.base import BaseTool
except ImportError:
    # 独立运行时的兜底基类
    class BaseTool:
        name = ""
        description = ""
        permission = "safe"
        enabled = True
        parameters = {}
        project_root = ""

        def __init__(self, project_root: str = ""):
            self.project_root = project_root

        def execute(self, arguments):
            raise NotImplementedError

        def get_schema(self):
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }


class WebSearchTool(BaseTool):
    """联网搜索工具（Bing CN）"""

    name = "web_search"
    description = (
        "通过必应搜索引擎搜索关键词,返回搜索结果列表。"
        "用于获取实时信息、新闻、技术文档等。国内可无障碍访问。"
    )
    permission = "safe"

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数(默认10)",
            },
        },
        "required": ["query"],
    }

    # ── Bing CN 搜索 URL ──────────────────────
    SEARCH_URL = "https://cn.bing.com/search"

    def execute(self, arguments: Dict[str, Any]) -> str:
        """执行联网搜索"""
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 10)

        if not query.strip():
            return "错误: 搜索关键词不能为空"

        try:
            # 构造请求参数
            params = {
                "q": query,                         # 搜索词
                "count": min(max_results, 50),      # Bing 每页最多约 50 条
                "setlang": "zh-Hans",               # 中文简体界面
                "FORM": "QBRE",                     # 避免不必要的重定向
            }

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            response = requests.get(
                self.SEARCH_URL,
                params=params,
                headers=headers,
                timeout=15,
                allow_redirects=True,
            )
            response.raise_for_status()

            html = response.text
            results = self._parse_results(html, max_results)

            if not results:
                return f"未找到相关结果\n查询: {query}\n\n提示: Bing 可能要求验证(如出现验证页面则无法解析)，可稍后重试。"

            # 格式化输出
            output = f"搜索结果: {query}\n"
            output += f"找到 {len(results)} 个结果\n"
            output += "=" * 60 + "\n\n"

            for i, result in enumerate(results, 1):
                output += f"{i}. {result['title']}\n"
                output += f"   URL: {result['url']}\n"
                if result.get("snippet"):
                    output += f"   摘要: {result['snippet']}\n"
                output += "\n"

            return output

        except requests.exceptions.Timeout:
            return "错误: 搜索请求超时(15秒),请稍后重试"
        except requests.exceptions.ConnectionError:
            return "错误: 网络连接失败,请检查网络设置"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            return f"错误: HTTP {status} - 请求被拒绝，可能触发了 Bing 的反爬机制，请稍后重试"
        except Exception as e:
            return f"搜索失败: {str(e)}"

    # ═══════════════════════════════════════════════
    #  HTML 解析
    # ═══════════════════════════════════════════════

    def _parse_results(self, html: str, max_results: int) -> list:
        """
        从 Bing CN 搜索结果 HTML 中提取结果列表。

        Bing 搜索结果的 DOM 结构（2024-2025）:

            <li class="b_algo" ...>
                <h2><a href="真实URL">标题</a></h2>
                <div class="b_caption">
                    <p class="b_lineclamp2">摘要文字</p>
                </div>
                <div class="b_attribution"><cite>显示的URL</cite></div>
            </li>

        解析策略:
          1. 用 'class="b_algo"' 分割，每个块 = 一个结果
          2. 在块内用正则提取 h2>a 的 href 和文本
          3. 在块内提取 p.b_lineclamp2 的文本作为摘要
          4. 在块内提取 cite 文本作为显示 URL（可选）
        """
        results = []

        # ── 步骤1: 按 b_algo 分割结果块 ──
        # 注意: 可能有 class="b_algo b_algoN" 等变体，统一用正则
        blocks = re.split(
            r'<li\s[^>]*\bclass="[^"]*\bb_algo\b[^"]*"[^>]*>',
            html,
        )

        # 第一个分割块是 <li> 之前的内容（搜索框/导航等），跳过
        for block in blocks[1:]:
            if len(results) >= max_results:
                break

            # 跳过非正常的结束块
            if "</li>" not in block:
                continue

            # 截取到 </li> 之前的内容
            li_end = block.find("</li>")
            if li_end > 0:
                block = block[:li_end]

            # ── 步骤2: 提取标题和链接 ──
            title, url = self._extract_title_link(block)
            if not title or not url:
                continue  # 没有有效标题/链接 → 跳过（可能是广告或非标准块）

            # ── 步骤3: 提取摘要 ──
            snippet = self._extract_snippet(block)

            # 清理 HTML 实体
            title = html_unescape(self._strip_tags(title))
            snippet = html_unescape(self._strip_tags(snippet))

            results.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": snippet.strip(),
            })

        return results

    def _extract_title_link(self, block: str):
        """
        从结果块中提取标题文字和链接 URL。

        Bing 的 h2>a 结构:
            <h2 class=""><a target="_blank" href="https://..." h="ID=...">标题</a></h2>

        两种可能:
          A) 标准: href 在 <a 标签内直接写明
          B) 有时 href 可能在 h 属性里通过重定向编码（较少见，本版不处理）
        """
        # 匹配 h2 内部（允许 class 等属性）
        h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.DOTALL)
        if not h2_match:
            return None, None

        h2_content = h2_match.group(1)

        # 匹配 <a ... href="URL" ...> 标题 </a>
        a_match = re.search(r'<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>', h2_content, re.DOTALL)
        if not a_match:
            return None, None

        url = a_match.group(1)
        title = a_match.group(2)

        return title, url

    def _extract_snippet(self, block: str) -> str:
        """
        从结果块中提取摘要文字。

        优先级:
          1. <p class="b_lineclamp2">  ← Bing 标准摘要
          2. <p class="b_lineclamp3">  ← 有些结果用三行
          3. <div class="b_caption">   ← 降级方案
          4. 整个块中的文本（最后兜底）
        """
        # 方案1: b_lineclamp2
        m = re.search(
            r'<p\s[^>]*\bclass="[^"]*\bb_lineclamp2\b[^"]*"[^>]*>(.*?)</p>',
            block,
            re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        # 方案2: b_lineclamp3
        m = re.search(
            r'<p\s[^>]*\bclass="[^"]*\bb_lineclamp3\b[^"]*"[^>]*>(.*?)</p>',
            block,
            re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        # 方案3: b_caption 内的任意 <p>
        caption_match = re.search(
            r'<div\s[^>]*\bclass="[^"]*\bb_caption\b[^"]*"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if caption_match:
            p_match = re.search(r'<p[^>]*>(.*?)</p>', caption_match.group(1), re.DOTALL)
            if p_match:
                return p_match.group(1).strip()
            return self._strip_tags(caption_match.group(1))

        return ""

    @staticmethod
    def _strip_tags(text: str) -> str:
        """移除 HTML 标签并清理空白"""
        # 移除所有 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 移除 HTML 实体（如 &amp; &lt; &ensp; &#0183; 等）
        text = re.sub(r'&[a-zA-Z]+;', '', text)
        text = re.sub(r'&#\d+;', '', text)
        # 合并多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# ═══════════════════════════════════════════════
#  独立测试入口
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "python hello world"
    print(f"正在搜索: {query}\n")
    tool = WebSearchTool()
    result = tool.execute({"query": query, "max_results": 5})
    print(result)
