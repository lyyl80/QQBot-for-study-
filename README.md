# MarsAI QQ Bot

基于 NoneBot2 的 QQ 机器人，支持 AI 对话功能。

## 功能特性

- 支持群聊和私聊 AI 对话
- 可切换云端模型（DeepSeek）和本地模型（Ollama）
- 简单的会话管理（内存中）

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

### 3. 运行机器人

```bash
python bot.py
```
## 依赖

- nonebot2
- nonebot-adapter-onebot
- openai (用于云端模型)
- ollama (用于本地模型)

## 许可证

仅供学习和个人使用。