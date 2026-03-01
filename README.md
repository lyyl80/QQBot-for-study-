# MarsAI QQ Bot

基于 NoneBot2 的 QQ 机器人，支持 AI 对话功能。

## 功能特性

- 支持群聊和私聊 AI 对话
- 可切换云端模型（DeepSeek）和本地模型（Ollama）
- 简单的会话管理（内存中）
- 长期记忆支持（自动总结和存储重要对话）
- 智能提醒功能（自然语言解析，支持重复提醒）
- 模型管理和预设角色切换
- 自动下载 Bilibili 视频（支持私聊和群聊发送）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 环境配置

复制 `.env.example`（如果存在）或创建 `.env` 文件，配置以下内容：

```bash
HOST=127.0.0.1
PORT=8080
SUPERUSERS=["你的QQ号"]
NICKNAME=["MarsAI"]
COMMAND_START=[""]
```

对于 AI 功能，设置 API 密钥：

```bash
# Windows
set DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Linux/Mac
export DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

对于 Bilibili 下载功能（可选）：
- 如果需要下载高清或会员视频，可以在 `~/.yt-dlp/cookies.txt` 放置 cookies 文件
- 建议安装 FFmpeg 以获得更好的视频兼容性
  - Windows：从 [FFmpeg官网](https://ffmpeg.org/download.html) 下载，解压后将 `bin` 目录添加到系统 PATH
  - Linux：`sudo apt install ffmpeg`（Debian/Ubuntu）或 `sudo yum install ffmpeg`（CentOS/RHEL）
  - macOS：`brew install ffmpeg`

### 3. 运行机器人

```bash
python bot.py
```

### 4. 使用命令

机器人支持以下命令（私聊直接发送，群聊需要@机器人）：

| 命令 | 功能描述 |
|------|----------|
| `/help` | 显示所有可用命令 |
| `/clear` | 清除当前会话历史 |
| `/prompt` | 显示或更新系统 prompt（`/prompt list` 会同时显示预设温度） |
| `/model` | 显示或切换 AI 模型 |
| `/memory` | 管理长期记忆 |
| `/reminder` | 设置和管理提醒 |
| `/summary` | 总结当前对话内容 |
| `/history` | 查看最近对话历史 |
| `/status` | 显示系统状态 |
| `/reset` | 重置对话 |
| `/temperature` | 查看或设置采样温度（0-2范围，值越高越随机） |

### B站视频下载功能
机器人自动检测 Bilibili 视频链接（支持多种链接格式），下载后发送视频文件到聊天窗口。

**详细命令说明**：请查看 [COMMANDS.md](COMMANDS.md) 获取完整文档和示例。

## 依赖

- nonebot2
- nonebot-adapter-onebot
- openai (用于云端模型)
- ollama (用于本地模型)
- yt-dlp (用于 Bilibili 视频下载)
- nonebot-plugin-apscheduler (用于提醒调度)

## 许可证

仅供学习和个人使用。