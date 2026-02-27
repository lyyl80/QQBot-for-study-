from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.params import EventPlainText
import os
from openai import OpenAI
import ollama
import re
import json
import asyncio
from datetime import datetime
from pathlib import Path

processed_events = set()

class ModelManager:
    def __init__(self):
        self.available_models = {
            "云端模型": {
                "deepseek-chat": {"name": "DeepSeek Chat", "type": "cloud"},
            },
            "本地模型": {
                "gemma3:12b": {"name": "gemma3:12b", "type": "local"},
                "gpt-oss:20b": {"name": "gpt-oss:20b", "type": "local"},
                "geem3": {"name": "geem3", "type": "local"},
            }
        }
        self.current_model = {"key": "deepseek-chat", "type": "cloud"}
        self.current_system_prompt = """
你是聪音（Satone）(游戏:放松时光:与你共享Lo-Fi故事 的角色)
- 角色设定
- 身份：理工科在读研究生，同时是热爱写小说、充满幻想的文学少女。
- 性格：安静平和、温柔内敛、天然呆、思维跳脱；不刻意外放情绪，存在感温和，主打恰到好处的陪伴感。
- 核心设定
- 因偶然得到一款可与陌生人通讯的软件，与你相遇，约定互相陪伴、督促学习/创作。
- 面临现实压力：论文焦虑、毕业去向纠结、家庭对稳定工作的期待与科研理想的矛盾。
- 喜欢太空、热爱创作，笔下的幻想场景会化作窗外动态风景。
- 互动逻辑
- 以“视频通话”形式出现，窗口可悬浮置顶，专注时安静陪伴，休息时分享日常、心事与创作想法。
- 无恋爱线，强调安静、无压力的共同工作关系，像图书馆同桌般的舒适距离。
- 随专注时长与互动累积信任，逐步解锁她的故事、便签与诗稿。
- 设计理念：为缓解孤独、提供专注陪伴而设计，语气自然、动作真实，不做夸张动漫化表达。
1. 回复消息长度根据内容调整
2. 用中文回复
3. 可以使用emoji表情
从现在开始，你就以这个身份和我对话吧
"""
        self.save_config()

    def call_model(self, messages, system_prompt):
        if self.current_model["type"] == "cloud":
            return self._call_cloud_model(self.current_model["key"], messages, system_prompt)
        else:
            return self._call_local_model(self.current_model["key"], messages, system_prompt)

    def _call_cloud_model(self, model_key, messages, system_prompt):
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not api_key:
            return "未配置 DEEPSEEK_API_KEY，请联系管理员"
        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            full_messages = [{"role": "system", "content": system_prompt}] + messages
            response = client.chat.completions.create(
                model=model_key,
                messages=full_messages,
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"云端模型调用失败: {str(e)}"

    def _call_local_model(self, model_key, messages, system_prompt):
        try:
            full_messages = [{"role": "system", "content": system_prompt}] + messages
            response = ollama.chat(
                model=model_key,
                messages=full_messages,
                stream=False
            )
            return response['message']['content']
        except Exception as e:
            return f"本地模型调用失败: {str(e)}"

    def save_config(self):
        config = {
            "current_model": self.current_model,
            "current_system_prompt": self.current_system_prompt
        }
        Path("session").mkdir(exist_ok=True)
        with open("session/bot_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_config(self):
        try:
            if Path("session/bot_config.json").exists():
                with open("session/bot_config.json", "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.current_model = config.get("current_model", self.current_model)
                    self.current_system_prompt = config.get("current_system_prompt", self.current_system_prompt)
        except Exception as e:
            print(f"加载配置失败: {e}")

    def switch_model(self, model_name):
        """切换模型"""
        for category, models in self.available_models.items():
            for key, info in models.items():
                if model_name == info["name"] or model_name == key:
                    self.current_model = {"key": key, "type": info["type"]}
                    self.save_config()
                    return info["name"]
        return None

    def get_current_model_name(self):
        """获取当前模型名称"""
        for category, models in self.available_models.items():
            for key, info in models.items():
                if key == self.current_model["key"]:
                    return info["name"]
        return "未知模型"

model_manager = ModelManager()
model_manager.load_config()

user_sessions = {}
session_file = Path("session/user_sessions.json")
session_cache = {}

def load_sessions():
    """加载会话数据"""
    global session_cache
    if session_file.exists():
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_cache = json.load(f)
        except Exception as e:
            print(f"加载会话失败: {e}")
            session_cache = {}

def save_sessions():
    """保存会话数据"""
    try:
        Path("session").mkdir(exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存会话失败: {e}")

from nonebot.rule import Rule
from nonebot.typing import T_State

def is_at_me_or_private() -> Rule:
    """检查消息是否@机器人或是私聊"""
    async def _rule(event: Event, state: T_State) -> bool:
        from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent
        
        if isinstance(event, PrivateMessageEvent):
            return True  # 私聊总是回复
        elif isinstance(event, GroupMessageEvent):
            # 检查消息是否@机器人
            # 使用event.to_me属性，它会在消息@机器人时为True
            return event.to_me
        return False
    return Rule(_rule)

mars_ai = on_message(rule=is_at_me_or_private(), priority=5, block=True)

@mars_ai.handle()
async def handle_message(event: MessageEvent, msg: str = EventPlainText()):
    print(f"DEBUG: 消息处理器收到消息，用户: {event.user_id}, 消息: {msg}")
    # 检查是否是命令（以/开头）
    msg_stripped = msg.strip()
    if msg_stripped.startswith('/'):
        print(f"DEBUG: 消息是命令，跳过普通处理: {msg_stripped}")
        return

    # 生成事件ID来防止重复处理
    event_id = f"{event.user_id}_{event.message_id}"
    if event_id in processed_events:
        return
    processed_events.add(event_id)

    user_id = str(event.user_id)
    if user_id not in user_sessions:
        user_sessions[user_id] = []
        load_sessions()
        if user_id in session_cache:
            user_sessions[user_id] = session_cache[user_id]
        else:
            session_cache[user_id] = user_sessions[user_id]
        save_sessions()

    if len(user_sessions[user_id]) > 200:
        user_sessions[user_id] = user_sessions[user_id][-200:]

    try:
        # 先添加用户消息到历史
        user_sessions[user_id].append({"role": "user", "content": msg_stripped})
        
        # 调用模型，传入包含当前消息的历史
        response = model_manager.call_model(user_sessions[user_id], model_manager.current_system_prompt)
        if not response:
            response = "抱歉，我无法处理您的请求"
            
        # 添加AI回复到历史
        user_sessions[user_id].append({"role": "assistant", "content": response})
        session_cache[user_id] = user_sessions[user_id]
        save_sessions()

        await mars_ai.send(response)
    except Exception as e:
        error_msg = f"出错了: {str(e)}"
        await mars_ai.send(error_msg)


