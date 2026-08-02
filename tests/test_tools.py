"""
工具系统测试脚本 - 验证所有内置工具
"""
import os
import sys
import json

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 验证路径
assert os.path.exists(os.path.join(PROJECT_ROOT, "func")), f"func目录不存在: {PROJECT_ROOT}"

from func.tools import ToolRegistry, ToolExecutor
from func.tools.builtin import (
    ReadTool, WriteTool, EditTool, GlobTool, GrepTool, BashTool
)


def test_all_tools():
    """测试所有内置工具"""
    print("=" * 70)
    print("工具系统测试 - 阶段2验证")
    print("=" * 70)
    print(f"项目根目录: {PROJECT_ROOT}\n")
    
    # 创建注册中心
    registry = ToolRegistry(project_root=PROJECT_ROOT)
    
    # 注册所有工具
    print("[1/7] 注册工具...")
    registry.register(ReadTool)
    registry.register(WriteTool)
    registry.register(EditTool)
    registry.register(GlobTool)
    registry.register(GrepTool)
    registry.register(BashTool)
    print(f"成功注册 {len(registry.get_all())} 个工具\n")
    
    # 创建执行器
    executor = ToolExecutor(registry)
    
    # 测试1: Read工具
    print("[2/7] 测试 ReadTool...")
    result = registry.execute("read", {"file_path": "README.md"})
    assert result.startswith("文件:"), f"ReadTool输出格式错误: {result[:100]}"
    assert "YOder" in result, "ReadTool未正确读取README"
    print("ReadTool: 通过\n")
    
    # 测试2: Glob工具
    print("[3/7] 测试 GlobTool...")
    result = registry.execute("glob", {"pattern": "*.py"})
    assert "错误" not in result, f"GlobTool失败: {result}"
    assert "找到" in result, "GlobTool输出格式错误"
    print("GlobTool: 通过\n")
    
    # 测试3: Grep工具
    print("[4/7] 测试 GrepTool...")
    result = registry.execute("grep", {"pattern": "def test", "file_pattern": "*.py"})
    assert "错误" not in result, f"GrepTool失败: {result}"
    print("GrepTool: 通过\n")
    
    # 测试4: Write工具
    print("[5/7] 测试 WriteTool...")
    test_file = "test_output.txt"
    test_content = "这是测试内容\n第二行\n第三行"
    result = registry.execute("write", {
        "file_path": test_file,
        "content": test_content
    })
    assert "成功" in result, f"WriteTool失败: {result}"
    print("WriteTool: 通过\n")
    
    # 测试5: Read刚写入的文件
    print("[6/7] 验证写入的文件...")
    result = registry.execute("read", {"file_path": test_file})
    assert test_content in result, "写入的文件内容不匹配"
    print("文件内容验证: 通过\n")
    
    # 测试6: Edit工具
    print("[7/7] 测试 EditTool...")
    result = registry.execute("edit", {
        "file_path": test_file,
        "old_text": "第二行",
        "new_text": "修改后的第二行"
    })
    assert "成功" in result, f"EditTool失败: {result}"
    
    # 验证修改
    result = registry.execute("read", {"file_path": test_file})
    assert "修改后的第二行" in result, "EditTool修改未生效"
    print("EditTool: 通过\n")
    
    # 测试8: Bash工具(安全命令)
    print("[8/8] 测试 BashTool...")
    result = registry.execute("bash", {"command": "echo 'Hello World'"})
    assert "错误" not in result, f"BashTool失败: {result}"
    assert "Hello World" in result or "退出码: 0" in result, "BashTool输出错误"
    print("BashTool: 通过\n")
    
    # 测试9: 安全限制
    print("[9/9] 测试安全限制...")
    
    # 测试黑名单路径
    result = registry.execute("read", {"file_path": "config/info.json"})
    assert "错误" in result and "敏感" in result, "黑名单限制失效"
    print("黑名单限制: 通过")
    
    # 测试危险命令
    result = registry.execute("bash", {"command": "rm -rf /"})
    assert "错误" in result and "危险" in result, "危险命令限制失效"
    print("危险命令限制: 通过")
    
    # 测试不支持的扩展名
    result = registry.execute("read", {"file_path": "icon.png"})
    assert "错误" in result and "不支持" in result, "扩展名限制失效"
    print("扩展名限制: 通过\n")
    
    # 清理测试文件
    try:
        test_path = os.path.join(PROJECT_ROOT, test_file)
        if os.path.exists(test_path):
            os.remove(test_path)
        print("测试文件已清理\n")
    except:
        pass
    
    print("=" * 70)
    print("所有测试通过! 阶段2完成")
    print("=" * 70)
    
    # 输出工具Schema示例
    print("\n工具Schema示例 (供Tool Calls使用):")
    schemas = registry.get_schemas()
    print(json.dumps(schemas[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    test_all_tools()
