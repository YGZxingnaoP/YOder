# YOder - AI 编程助手

<p align="center">
  <img src="icon.png" alt="YOder Icon" width="200" height="200" />
</p>

<p align="center">
  <b>基于多轮 Tool Calls 的多模型 AI 编程助手</b><br/>
  支持 阿里通义(Qwen) / DeepSeek / 智谱(GLM) / Kimi 四大平台
</p>

---

## 📖 简介

YOder 是一款**桌面版 AI 编程助手**，采用「Python FastAPI 后端 + WebGL 前端 + pywebview 桌面壳」架构。
它不仅能像普通聊天机器人一样对话，更能**自主调用工具**完成编程任务：读文件、写代码、搜索网页、执行命令，全程可视化展示思考过程与任务进度。

- 🎨 **动态 WebGL 背景** + 自定义壁纸，颜值在线
- 🔧 **10+ 内置工具**，AI 可自主调用完成任务
- 🧠 **TODOLIST 驱动模式**：AI 自主拆解任务、逐步执行、实时更新进度
- ⛓ **旧版思维链模式**：四阶段长文/代码生成管线
- 🔄 **多模型适配**：一个界面切换四大 AI 平台
- 💾 **记忆系统**：AI 概括历史对话，后续对话自动注入上下文
- 📁 **文件系统访问**：加载文件夹，AI 可直接读写项目代码

## 🏗 项目架构

```
YOder/
├── func/                    # Python 后端源码
│   ├── api/                 # FastAPI 路由层
│   │   ├── main.py          #   App 入口（挂载路由/静态资源）
│   │   ├── chat_routes.py   #   对话核心（标准模式 + 思维链桥接）
│   │   ├── chat_mgmt.py     #   对话管理（增删改查）
│   │   ├── config_routes.py #   全局配置
│   │   ├── memory_routes.py #   记忆系统
│   │   ├── tools_routes.py  #   工具开关
│   │   ├── browser_routes.py#   浏览器/文件系统访问
│   │   └── wallpaper_routes.py # 壁纸管理
│   ├── agent/               # Agent 模式
│   │   ├── goal_executor.py #   TODOLIST 驱动执行器
│   │   └── agent_worker.py  #   Agent 工作器
│   ├── chainmode/           # 旧版思维链四阶段管线
│   │   ├── agent_core.py    #   编排器
│   │   └── taskchunks/      #   阶段一~四实现
│   ├── chatbot/             # 多模型适配层
│   │   ├── port.py          #   ChatClient（流式对话）
│   │   └── *_tools_port.py  #   各平台 Function Calling 适配
│   ├── tools/               # 工具系统
│   │   ├── registry.py      #   工具注册中心
│   │   ├── executor.py      #   工具执行器
│   │   └── builtin/         #   10+ 内置工具
│   └── files_reader/        # 文件读取/Token 计算
├── frontend/                # 前端源码（Vite + Vanilla JS）
│   └── src/
│       ├── main.js          #   应用入口
│       ├── managers/        #   Chat/Config/UI 管理器
│       └── webgl/           #   WebGL 动态背景
├── config/                  # 运行时配置（不提交 git）
│   ├── info.json            #   API Key 与全局参数
│   └── tools.json           #   工具开关状态
├── records/                 # 对话记录（每个会话一个文件夹）
├── wallpapers/              # 壁纸图片与状态
├── tests/                   # 后端单元测试
├── build.bat                # 一键打包脚本（PyInstaller）
├── start_api.bat            # 源码模式启动脚本
└── requirements.txt         # Python 依赖
```

## ⚙️ 两种使用方式

### 方式一：直接使用打包版（推荐普通用户）

进入 `dist/` 目录，双击 `start.bat` 或 `YOder.exe` 即可启动，无需安装 Python / Node.js。

### 方式二：源码运行（开发者）

```bash
# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 启动后端服务
start_api.bat
# 或手动执行：
python -m uvicorn func.api.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 浏览器访问
http://localhost:8000
```

> 前端开发模式（需 Node.js）：进入 `frontend/` 后执行 `npm install && npm run dev`，Vite 会启动热更新开发服务器。

## 🔑 首次使用配置

1. 启动 YOder 后，点击底部工具栏的 **⚙ 全局设置**
2. 在「平台」下拉框选择 AI 服务商：**阿里 / DeepSeek / 智谱 / Kimi**
3. 填入对应平台的 **API Key**（在各自官网申请）
4. 选择模型、调节参数，点击保存
5. 在输入框输入消息即可开始对话

> 💡 各平台模型参考：阿里 `qwen-max` / `qwen-plus`，DeepSeek `deepseek-chat`，智谱 `glm-4`，Kimi `moonshot-v1-8k`

## 🧰 核心功能

### 1. 多轮工具调用（标准模式）

```
用户提问 → AI 思考 → 调用工具 → 获取结果 → AI 继续思考
                                    ↓
                            继续调用工具（最多 16 轮）
                                    ↓
                              输出最终回复
```

AI 的思考过程（reasoning/thinking）以**可折叠面板**形式实时展示，可展开查看完整推理链路。

### 2. Agent 模式（TODOLIST 驱动）

开启后 AI 自主拆解任务：

1. AI 分析用户意图，创建 TODOLIST 任务列表
2. 逐步执行任务，实时更新状态（待办 → 进行中 → 完成）
3. 每完成一步可调用工具验证结果
4. 最多 16 轮迭代防止死循环
5. 前端实时渲染任务进度

### 3. 旧版思维链模式

面向长文/代码生成的**四阶段管线**：框架构建 → 逐任务填充 → 内容审查（最多 6 次） → 最终输出。适合一次性生成完整项目或长文档。

### 4. 记忆系统

- **记忆概括**：手动触发 AI 概括历史对话，后续对话自动注入作为上下文
- **单轮删除**：可删除对话中的某一轮（user + assistant + tool 消息），记忆标记自动调整
- **对话持久化**：对话记录、模型配置、壁纸选择均独立存储

### 5. 文件系统访问

在右侧栏「文件列表」中加载文件夹路径，AI 即可读写该目录下的文件；也可通过 📎 附件按钮直接上传文件参与对话。

### 6. 壁纸系统

隐藏入口：**连续点击发送按钮 5 次**，可设置 WebGL 动态渐变 / 纯黑背景 / 自定义图片壁纸，并调节模糊度与透明度。

## 🛠 内置工具（11 个）

| 工具 | 功能 | 说明 |
|------|------|------|
| read | 文件读取 | 白名单扩展名、路径限制 |
| write | 文件写入 | 自动创建目录 |
| edit | 精确编辑 | 文本替换、唯一性检查 |
| glob | 文件搜索 | `**` 递归匹配 |
| grep | 内容搜索 | 正则表达式 |
| bash | Shell 命令 | 白名单 + 用户确认 |
| web_search | 联网搜索 | 搜索引擎查询 |
| web_browse | 网页浏览 | trafilatura 正文提取 |
| selenium_browse | 动态网页浏览 | 支持 JS 渲染页面 |
| edge_check | 浏览器检测 | Edge WebDriver 引导 |
| todolist | 任务规划 | AI 自主创建和管理 |

每个工具拥有三级权限：`safe`（自动执行）、`moderate`（需确认）、`dangerous`（强制确认）。可在「🔧 工具箱」中开关各工具。

## 🔧 打包发布

```bash
build.bat
```

脚本会自动完成：配置嵌入式 Python → 安装依赖 → 构建前端 → PyInstaller 打包为单文件 exe，输出到 `dist/` 目录。

## 🧪 测试

```bash
python -m pytest tests/
```

## 📄 面向用户教程

👉 完整的使用教程见 [USER_GUIDE.md](USER_GUIDE.md)

## 📝 License

本项目仅供学习交流使用，请遵守各 AI 平台的服务条款。
