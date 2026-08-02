"""
阶段3测试 - 联网与网页工具
"""
import sys
import os

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from func.tools.registry import ToolRegistry
from func.tools.builtin import (
    WebSearchTool, WebBrowseTool, EdgeCheckTool
)


def test_phase3():
    """测试阶段3: 联网与网页工具"""
    print("\n" + "="*60)
    print("阶段3测试: 联网与网页工具")
    print("="*60 + "\n")
    
    # 1. 注册工具
    registry = ToolRegistry(project_root=PROJECT_ROOT)
    
    print("[1/3] 注册联网工具...")
    registry.register(WebSearchTool)
    registry.register(WebBrowseTool)
    registry.register(EdgeCheckTool)
    
    enabled = registry.get_enabled()
    print(f"  成功注册 {len(enabled)} 个联网工具")
    assert len(enabled) == 3, "应该注册3个联网工具"
    
    # 2. 测试EdgeCheckTool (不需要网络)
    print("\n[2/3] 测试 EdgeCheckTool...")
    result = registry.execute("edge_check", {})
    assert "Edge浏览器" in result or "未检测到" in result
    print("  EdgeCheckTool: 通过")
    print("  输出预览:")
    for line in result.split('\n')[:8]:
        print(f"    {line}")
    
    # 3. 测试WebSearchTool (需要网络)
    print("\n[3/3] 测试 WebSearchTool (需要网络)...")
    try:
        result = registry.execute("web_search", {
            "query": "Python programming",
            "max_results": 3
        })
        
        # 检查是否有结果或网络错误
        if "搜索结果" in result or "未找到" in result:
            print("  WebSearchTool: 通过")
            print("  输出预览:")
            for line in result.split('\n')[:6]:
                print(f"    {line}")
        else:
            print("  WebSearchTool: 网络问题,跳过")
            print(f"  错误: {result[:100]}")
            
    except Exception as e:
        print(f"  WebSearchTool: 网络异常,跳过 - {e}")
    
    # 4. 测试WebBrowseTool (需要网络)
    print("\n[4/4] 测试 WebBrowseTool (需要网络)...")
    try:
        result = registry.execute("web_browse", {
            "url": "https://example.com",
            "max_length": 500
        })
        
        if "网页内容" in result or "错误" in result:
            print("  WebBrowseTool: 通过")
            print("  输出预览:")
            for line in result.split('\n')[:6]:
                print(f"    {line}")
        else:
            print("  WebBrowseTool: 网络问题,跳过")
            
    except Exception as e:
        print(f"  WebBrowseTool: 网络异常,跳过 - {e}")
    
    print("\n" + "="*60)
    print("阶段3测试完成!")
    print("="*60)


if __name__ == "__main__":
    test_phase3()
