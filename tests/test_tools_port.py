"""
阶段5测试 - Tool Calls 多模型适配
"""
import sys
import os

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from func.chatbot.tools_port_factory import ToolsPortFactory
from func.chatbot.qwen_tools_port import QwenToolsPort
from func.chatbot.deepseek_tools_port import DeepSeekToolsPort
from func.chatbot.kimi_tools_port import KimiToolsPort
from func.chatbot.glm_tools_port import GLMToolsPort


def test_phase5():
    """测试阶段5: Tool Calls 多模型适配"""
    print("\n" + "="*60)
    print("阶段5测试: Tool Calls 多模型适配")
    print("="*60 + "\n")
    
    # 1. 测试工厂类创建
    print("[1/3] 测试ToolsPortFactory...")
    
    test_api_key = "test_key_123"
    
    # 测试创建各平台
    try:
        qwen_port = ToolsPortFactory.create("阿里", test_api_key)
        assert isinstance(qwen_port, QwenToolsPort)
        print("  创建 QwenToolsPort: 通过")
        
        deepseek_port = ToolsPortFactory.create("DeepSeek", test_api_key)
        assert isinstance(deepseek_port, DeepSeekToolsPort)
        print("  创建 DeepSeekToolsPort: 通过")
        
        kimi_port = ToolsPortFactory.create("Kimi", test_api_key)
        assert isinstance(kimi_port, KimiToolsPort)
        print("  创建 KimiToolsPort: 通过")
        
        glm_port = ToolsPortFactory.create("智谱", test_api_key)
        assert isinstance(glm_port, GLMToolsPort)
        print("  创建 GLMToolsPort: 通过")
        
    except Exception as e:
        print(f"  工厂类创建失败: {e}")
        return
    
    # 2. 测试异常处理
    print("\n[2/3] 测试异常处理...")
    
    try:
        # 测试未知平台
        ToolsPortFactory.create("未知平台", test_api_key)
        print("  错误: 应该抛出异常但未抛出")
    except ValueError as e:
        if "未知平台" in str(e):
            print("  未知平台异常: 通过")
        else:
            print(f"  异常信息错误: {e}")
    
    # 3. 测试接口一致性
    print("\n[3/3] 测试接口一致性...")
    
    ports = [qwen_port, deepseek_port, kimi_port, glm_port]
    port_names = ["Qwen", "DeepSeek", "Kimi", "GLM"]
    
    for port, name in zip(ports, port_names):
        # 检查是否有chat_with_tools方法
        if hasattr(port, "chat_with_tools"):
            print(f"  {name} chat_with_tools方法: 存在")
        else:
            print(f"  {name} chat_with_tools方法: 缺失")
            continue
        
        # 检查方法签名
        import inspect
        sig = inspect.signature(port.chat_with_tools)
        params = list(sig.parameters.keys())
        
        required_params = ["messages", "tools", "callback"]
        missing = [p for p in required_params if p not in params]
        
        if not missing:
            print(f"  {name} 必需参数: 完整")
        else:
            print(f"  {name} 缺少参数: {missing}")
    
    print("\n" + "="*60)
    print("阶段5测试完成! 4个模型的ToolsPort均已正确创建")
    print("="*60)
    print("\n说明:")
    print("- 实际调用需要真实API Key")
    print("- 工具调用功能需要配合ToolExecutor使用")
    print("- Kimi需要手动拼接delta.tool_calls")
    print("- Qwen/GLM支持tool_stream直接拼接")


if __name__ == "__main__":
    test_phase5()
