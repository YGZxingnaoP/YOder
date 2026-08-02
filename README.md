# YOder - AI编程助手

<p align="center">
  <img src="icon.png" alt="YOder Icon" width="512" height="512" />
</p>

基于多轮 Tool Calls 的多模型 AI 编程助手，支持 Qwen、DeepSeek、Kimi、GLM 四大平台。

## 核心逻辑

### 多轮工具调用

YOder 的核心交互循环：

```
用户提问 → AI思考 → 调用工具 → 获取结果 → AI继续思考
                                    ↓ (还有工具需要调用)
                              继续调用工具（最多10轮）
                                    ↓ (无更多工具调用)
                              输出最终回复
```

- 每轮 AI 调用后检查是否有 `tool_calls`，有则执行工具并将结果追加到消息历史，继续下一轮
- 达到 10 轮上限时，系统注入提示消息告知 AI，并以 `tools=[]` 做最终调用，强制 AI 基于已有结果生成总结
- 全程流式输出，通过 `\x01`/`\x02` 前缀区分思考内容与正式回复

### 思考内容折叠

AI 的思考过程（reasoning/thinking）以可折叠面板形式展示，用户可展开查看 AI 的推理链路。历史消息回看时同样支持折叠渲染。

### Agent 模式（TODOLIST 驱动）

开启 Agent 模式后，AI 自主拆解任务：

1. AI 分析用户意图，创建 TODOLIST 任务列表
2. 逐步执行任务，实时更新状态（待办→进行中→完成）
3. 每完成一步可调用工具验证结果
4. 最多 20 次迭代防止死循环
5. 前端实时渲染任务进度

## 内置工具（10个）

| 工具 | 功能 | 特性 |
|------|------|------|
| read | 文件读取 | 白名单扩展名、路径限制 |
| write | 文件写入 | 自动创建目录 |
| edit | 精确编辑 | 文本替换、相似匹配提示、唯一性检查 |
| glob | 文件搜索 | `**` 递归匹配、返回文件大小 |
| grep | 内容搜索 | 正则表达式 |
| bash | Shell命令 | 白名单 + 用户确认 |
| web_search | 联网搜索 | DuckDuckGo |
| web_browse | 网页浏览 | trafilatura 内容提取 |
| edge_check | 浏览器检测 | Edge WebDriver 下载引导 |
| todolist | 任务规划 | AI 自主创建和管理 |

每个工具拥有三级权限：`safe`（自动执行）、`moderate`（需确认）、`dangerous`（强制确认）。

## 多模型适配

四个平台各自独立适配，统一使用 OpenAI Function Calling 格式：

- **Qwen** — tool_stream 直接拼接
- **DeepSeek** — 标准流式 + reasoning_effort 控制思考深度
- **Kimi** — 手动拼接 delta.tool_calls
- **GLM** — tool_stream 直接拼接

支持对话级配置覆盖：每个对话可独立设置模型、参数、thinking_level，不受全局配置影响。

## 记忆系统

- **记忆概括**：手动触发对历史对话的 AI 概括，概括内容在后续对话中作为上下文注入
- **单轮删除**：可删除对话中的某一轮（user + assistant + tool 消息），记忆标记自动调整
- **对话持久化**：对话记录、模型配置、壁纸选择均独立存储

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
start_api.bat
# 或
python -m uvicorn func.api.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000

## 配置

编辑 `config/info.json` 设置 API Key 和默认参数：

```json
{
  "api_keys": {
    "阿里": "your_qwen_key",
    "DeepSeek": "your_deepseek_key",
    "智谱": "your_glm_key",
    "Kimi": "your_kimi_key"
  },
  "platform": "阿里",
  "model": "qwen-max",
  "max_tokens": 65536,
  "temperature": 0.7,
  "thinking_level": "high"
}
```
