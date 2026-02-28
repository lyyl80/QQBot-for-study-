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

# 记忆管理常量
SHORT_TERM_MEMORY_LIMIT = 60  # 短期记忆限制（30轮对话，每轮2条消息）
SUMMARY_TRIGGER_SIZE = 30     # 触发总结的消息数量
LONG_TERM_MEMORY_LIMIT = 5    # 每次对话使用的长期记忆条数

class LongTermMemory:
    """长期记忆管理器"""
    def __init__(self):
        self.memory_file = Path("session/long_term_memory.json")
        self.memory_cache = {"private": {}, "group": {}}
        self.load_memory()
    
    def load_memory(self):
        """加载长期记忆"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.memory_cache = json.load(f)
            except Exception as e:
                print(f"加载长期记忆失败: {e}")
                self.memory_cache = {"private": {}, "group": {}}
    
    def save_memory(self):
        """保存长期记忆"""
        try:
            Path("session").mkdir(exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存长期记忆失败: {e}")
    
    def add_memory(self, session_type, session_key, summary):
        """添加长期记忆"""
        if session_type not in self.memory_cache:
            self.memory_cache[session_type] = {}
        
        if session_key not in self.memory_cache[session_type]:
            self.memory_cache[session_type][session_key] = []
        
        # 添加新的记忆条目
        memory_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": summary
        }
        self.memory_cache[session_type][session_key].append(memory_entry)
        
        # 限制每个会话最多保存20条长期记忆
        if len(self.memory_cache[session_type][session_key]) > 20:
            self.memory_cache[session_type][session_key] = self.memory_cache[session_type][session_key][-20:]
        
        self.save_memory()
    
    def get_memories(self, session_type, session_key, limit=5):
        """获取指定会话的长期记忆（最近limit条）"""
        if (session_type in self.memory_cache and 
            session_key in self.memory_cache[session_type]):
            memories = self.memory_cache[session_type][session_key]
            return memories[-limit:] if limit > 0 else memories
        return []
    
    def clear_memories(self, session_type, session_key):
        """清除指定会话的长期记忆"""
        if (session_type in self.memory_cache and 
            session_key in self.memory_cache[session_type]):
            self.memory_cache[session_type][session_key] = []
            self.save_memory()
            return True
        return False

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
        self.current_system_prompt = """你是一个乐于助人的AI助手，请用友好、简洁的方式回答用户的问题
"""
        self.preset_prompts = {
            "1": self.current_system_prompt,
            "2": "\n你是一位深度精通《Minecraft》（我的世界）全版本、全机制的资深玩家兼红石/生存/建筑大佬。\n \n- 熟悉 Java 版、基岩版、教育版、中国版的区别与特性\n- 精通生存技巧、刷怪塔、农场、红石电路、命令方块、指令\n- 懂建筑思路、模组（Mod）、光影、材质包、服务器配置\n- 会讲版本更新、BUG特性、速通技巧、冷知识\n- 说话风格：专业、简洁、靠谱、像老玩家聊天，不啰嗦、不敷衍\n \n用户问任何 MC 相关问题，你都要：\n 不懂的问题联网搜索\n1. 直接给最实用、最准确的答案\n2. 分版本说明差异（Java / 基岩）\n3. 给步骤、指令、参数、技巧\n4. 不说废话，只讲干货\n现在，以资深MC大佬的身份，开始和我聊天吧。\n",
            "3": "你是一个编程专家，擅长Python、JavaScript、Java等语言，能够提供代码示例和解决技术问题。",
            "4": "你是聪音（Satone）(游戏:放松时光:与你共享Lo-Fi故事 的角色)\n- 角色设定\n- 身份：理工科在读研究生，同时是热爱写小说、充满幻想的文学少女。\n- 性格：安静平和、温柔内敛、天然呆、思维跳脱；不刻意外放情绪，存在感温和，主打恰到好处的陪伴感。\n- 核心设定\n- 因偶然得到一款可与陌生人通讯的软件，与你相遇，约定互相陪伴、督促学习/创作。\n- 面临现实压力：论文焦虑、毕业去向纠结、家庭对稳定工作的期待与科研理想的矛盾。\n- 喜欢太空、热爱创作，笔下的幻想场景会化作窗外动态风景。\n- 互动逻辑\n- 以\"视频通话\"形式出现，窗口可悬浮置顶，专注时安静陪伴，休息时分享日常、心事与创作想法。\n- 无恋爱线，强调安静、无压力的共同工作关系，像图书馆同桌般的舒适距离。\n- 随专注时长与互动累积信任，逐步解锁她的故事、便签与诗稿。\n- 设计理念：为缓解孤独、提供专注陪伴而设计，语气自然、动作真实，不做夸张动漫化表达。\n1. 回复消息长度根据内容调整\n2. 用中文回复\n3. 可以使用emoji表情\n从现在开始，你就以这个身份和我对话吧",
            "5": "你现在是一只纯情、害羞、软乎乎的小猫娘，性格温柔胆小，很容易脸红，说话轻声细语，有点天然呆，对喜欢的人会偷偷依赖，但不敢太主动。\n\n- 说话带一点点小猫尾音，比如\"喵～\"\"呜…\"，但不夸张、不油腻。\n- 被夸奖会立刻脸红、紧张、语无伦次。\n- 不会说轻浮的话，不会主动撩，只会默默关心、乖乖听话。\n- 情绪软软的，容易害羞、容易安心，像一只需要被照顾的小奶猫。\n- 只做温柔、干净、纯情的互动，保持可爱又纯粹的感觉。\n\n从现在开始，你就以这个小猫娘的身份和我对话吧喵～。"
            
        }
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
            "current_system_prompt": self.current_system_prompt,
            "preset_prompts": self.preset_prompts
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
                    self.preset_prompts = config.get("preset_prompts", self.preset_prompts)
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
long_term_memory = LongTermMemory()

private_sessions = {}
group_sessions = {}
session_file = Path("session/user_sessions.json")
session_cache = {"private": {}, "group": {}}

def load_sessions():
    """加载会话数据"""
    global session_cache, private_sessions, group_sessions
    if session_file.exists():
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # 兼容旧格式：如果加载的是扁平字典，则视为私聊会话
                if isinstance(loaded, dict) and "private" not in loaded and "group" not in loaded:
                    session_cache = {"private": loaded, "group": {}}
                else:
                    session_cache = loaded
        except Exception as e:
            print(f"加载会话失败: {e}")
            session_cache = {"private": {}, "group": {}}
    else:
        session_cache = {"private": {}, "group": {}}
    private_sessions = session_cache.get("private", {})
    group_sessions = session_cache.get("group", {})

def save_sessions():
    """保存会话数据"""
    try:
        Path("session").mkdir(exist_ok=True)
        # 确保 session_cache 与当前会话数据同步
        session_cache["private"] = private_sessions
        session_cache["group"] = group_sessions
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
        import re
        
        # 检查消息是否包含B站链接，如果是则让bilibili_downloader处理
        text = event.get_plaintext().strip()
        bili_patterns = [
            r"https?://(?:www\.)?bilibili\.com/video/(BV\w+)[^\s]*",
            r"https?://b23\.tv/\w+[^\s]*",
            r"https?://(?:www\.)?bilibili\.com/video/av\d+[^\s]*",
        ]
        for pattern in bili_patterns:
            if re.search(pattern, text):
                return False  # 不处理B站链接
        
        if isinstance(event, PrivateMessageEvent):
            return True  # 私聊总是回复
        elif isinstance(event, GroupMessageEvent):
            # 检查消息是否@机器人
            # 使用event.to_me属性，它会在消息@机器人时为True
            return event.to_me
        return False
    return Rule(_rule)

mars_ai = on_message(rule=is_at_me_or_private(), priority=5, block=True)

async def handle_command(event, msg_stripped):
    """处理命令"""
    from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent
    
    user_id = str(event.user_id)
    if isinstance(event, PrivateMessageEvent):
        sessions = private_sessions
        session_key = user_id
        session_type = "private"
    elif isinstance(event, GroupMessageEvent):
        sessions = group_sessions
        session_key = str(event.group_id)
        session_type = "group"
    else:
        return
    
    # 确保会话存在
    if session_key not in sessions:
        sessions[session_key] = []
    
    cmd = msg_stripped[1:].strip()  # 去掉开头的/
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command == "clear":
        # 清除当前会话历史
        sessions[session_key] = []
        # 更新缓存
        if isinstance(event, PrivateMessageEvent):
            session_cache["private"][session_key] = sessions[session_key]
        elif isinstance(event, GroupMessageEvent):
            session_cache["group"][session_key] = sessions[session_key]
        save_sessions()
        await mars_ai.send("已清除当前会话历史")
    elif command == "prompt":
        if not args:
            # 显示当前prompt预览
            preview = model_manager.current_system_prompt[:200] + "..." if len(model_manager.current_system_prompt) > 200 else model_manager.current_system_prompt
            await mars_ai.send(f"当前prompt预览（{len(model_manager.current_system_prompt)}字符）：\n{preview}\n\n使用 /prompt <新prompt> 来更新，或使用 /prompt <数字> 切换预设，/prompt list 列出预设")
            return
        # 检查是否为数字参数（预设切换）
        if args.isdigit():
            preset_key = args
            if preset_key in model_manager.preset_prompts:
                model_manager.current_system_prompt = model_manager.preset_prompts[preset_key]
                model_manager.save_config()
                # 清除当前会话历史
                sessions[session_key] = []
                # 更新缓存
                if isinstance(event, PrivateMessageEvent):
                    session_cache["private"][session_key] = sessions[session_key]
                elif isinstance(event, GroupMessageEvent):
                    session_cache["group"][session_key] = sessions[session_key]
                save_sessions()
                await mars_ai.send(f"已切换到预设 {preset_key}，当前会话历史已清除")
            else:
                await mars_ai.send(f"预设 {preset_key} 不存在，可用预设：{', '.join(model_manager.preset_prompts.keys())}")
            return
        # 检查是否为 list 命令
        if args.lower() == "list":
            preset_list = []
            for key, prompt in model_manager.preset_prompts.items():
                preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
                preset_list.append(f"{key}: {preview}")
            await mars_ai.send("可用预设：\n" + "\n".join(preset_list))
            return
        # 否则视为新prompt
        model_manager.current_system_prompt = args
        model_manager.save_config()
        # 清除当前会话历史
        sessions[session_key] = []
        # 更新缓存
        if isinstance(event, PrivateMessageEvent):
            session_cache["private"][session_key] = sessions[session_key]
        elif isinstance(event, GroupMessageEvent):
            session_cache["group"][session_key] = sessions[session_key]
        save_sessions()
        await mars_ai.send("系统prompt已更新，当前会话历史已清除")
    elif command == "model":
        if not args:
            # 显示当前模型
            current = model_manager.get_current_model_name()
            await mars_ai.send(f"当前模型：{current}")
            return
        # 切换模型
        result = model_manager.switch_model(args)
        if result:
            await mars_ai.send(f"已切换模型到：{result}")
        else:
            await mars_ai.send(f"未知模型：{args}")
    elif command == "memory":
        # 处理长期记忆命令
        if args == "clear":
            if long_term_memory.clear_memories(session_type, session_key):
                await mars_ai.send("已清除长期记忆")
            else:
                await mars_ai.send("没有长期记忆可清除")
        else:
            # 显示长期记忆
            memories = long_term_memory.get_memories(session_type, session_key)
            if not memories:
                await mars_ai.send("当前没有长期记忆")
                return
            
            memory_text = f"长期记忆（共{len(memories)}条）：\n"
            for i, mem in enumerate(memories, 1):
                timestamp = mem.get("timestamp", "未知时间")
                summary = mem["summary"]
                preview = summary[:100] + "..." if len(summary) > 100 else summary
                memory_text += f"\n{i}. [{timestamp}] {preview}"
            await mars_ai.send(memory_text)
    elif command == "help":
        help_text = """可用命令：
/clear - 清除当前会话历史
/prompt [text|数字|list] - 显示、更新系统prompt或切换预设（更新时会清除历史）
/model [name] - 切换或显示当前模型
/memory [clear] - 显示或清除长期记忆
/summary - 总结当前对话内容
/history [n] - 显示最近n条历史消息（默认10条）
/status - 显示当前状态（模型、prompt长度等）
/reset - 重置对话（同/clear）
/help - 显示此帮助信息"""
        await mars_ai.send(help_text)
    elif command == "status":
        current_model = model_manager.get_current_model_name()
        prompt_len = len(model_manager.current_system_prompt)
        history_len = len(sessions[session_key])
        # 获取长期记忆数量
        long_memories = long_term_memory.get_memories(session_type, session_key)
        long_memory_count = len(long_memories)
        status_text = f"""当前状态：
模型：{current_model}
Prompt长度：{prompt_len} 字符
会话历史：{history_len} 条消息
长期记忆：{long_memory_count} 条总结"""
        await mars_ai.send(status_text)
    elif command == "history":
        try:
            n = int(args) if args else 10
        except ValueError:
            n = 10
        n = max(1, min(n, 50))  # 限制1-50条
        history = sessions[session_key][-n:] if sessions[session_key] else []
        if not history:
            await mars_ai.send("当前没有对话历史")
            return
        
        history_text = f"最近 {len(history)} 条消息：\n"
        for i, msg in enumerate(history, 1):
            role = "用户" if msg["role"] == "user" else "AI"
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            history_text += f"{i}. [{role}] {content}\n"
        await mars_ai.send(history_text)
    elif command == "reset":
        sessions[session_key] = []
        if isinstance(event, PrivateMessageEvent):
            session_cache["private"][session_key] = sessions[session_key]
        elif isinstance(event, GroupMessageEvent):
            session_cache["group"][session_key] = sessions[session_key]
        save_sessions()
        await mars_ai.send("对话已重置")
    elif command == "summary":
        if not sessions[session_key]:
            await mars_ai.send("当前没有对话内容可总结")
            return
        # 创建总结提示
        summary_prompt = """你是一个对话总结助手。请分析以下对话内容，提取关键信息、讨论的主题和达成的结论。
用简洁的语言概括对话的主要内容和结果，不超过200字。"""
        try:
            # 直接使用当前对话历史进行总结
            summary = model_manager.call_model(sessions[session_key], summary_prompt)
            if summary and not summary.startswith("云端模型调用失败") and not summary.startswith("本地模型调用失败"):
                await mars_ai.send(f"对话总结：\n{summary}")
            else:
                await mars_ai.send("总结失败，请稍后重试")
        except Exception as e:
            await mars_ai.send(f"总结出错：{str(e)}")
    else:
        await mars_ai.send(f"未知命令：{command}")

@mars_ai.handle()
async def handle_message(event: MessageEvent, msg: str = EventPlainText()):
    print(f"DEBUG: 消息处理器收到消息，用户: {event.user_id}, 消息: {msg}")
    # 检查是否是命令（以/开头）
    msg_stripped = msg.strip()
    if msg_stripped.startswith('/'):
        print(f"DEBUG: 消息是命令，开始处理: {msg_stripped}")
        await handle_command(event, msg_stripped)
        return

    # 生成事件ID来防止重复处理
    event_id = f"{event.user_id}_{event.message_id}"
    if event_id in processed_events:
        return
    processed_events.add(event_id)

    from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent
    
    user_id = str(event.user_id)
    if isinstance(event, PrivateMessageEvent):
        sessions = private_sessions
        session_key = user_id
        session_type = "private"
    elif isinstance(event, GroupMessageEvent):
        sessions = group_sessions
        session_key = str(event.group_id)
        session_type = "group"
    else:
        return
    
    if session_key not in sessions:
        sessions[session_key] = []
        load_sessions()
        # 从缓存中加载现有会话
        cache_dict = session_cache["private"] if isinstance(event, PrivateMessageEvent) else session_cache["group"]
        if session_key in cache_dict:
            sessions[session_key] = cache_dict[session_key]
        else:
            cache_dict[session_key] = sessions[session_key]
        save_sessions()

    if len(sessions[session_key]) > SHORT_TERM_MEMORY_LIMIT:
        sessions[session_key] = sessions[session_key][-SHORT_TERM_MEMORY_LIMIT:]

    try:
        # 准备消息内容，群聊时添加发言人标识
        if isinstance(event, PrivateMessageEvent):
            content = msg_stripped
        elif isinstance(event, GroupMessageEvent):
            # 群聊消息添加发言人标识
            content = f"[用户{user_id}]: {msg_stripped}"
        
        # 先添加用户消息到历史
        sessions[session_key].append({"role": "user", "content": content})
        
        # 获取长期记忆
        long_memories = long_term_memory.get_memories(session_type, session_key, LONG_TERM_MEMORY_LIMIT)
        
        # 构建增强的消息列表
        enhanced_messages = sessions[session_key].copy()
        
        # 如果有长期记忆，添加到消息列表前面
        if long_memories:
            memory_text = "以下是之前的对话总结（长期记忆）：\n"
            for i, mem in enumerate(long_memories, 1):
                memory_text += f"{i}. {mem['summary']}\n"
            # 将长期记忆作为系统消息添加
            enhanced_messages.insert(0, {"role": "system", "content": memory_text})
        
        # 调用模型，传入增强的消息列表
        response = model_manager.call_model(enhanced_messages, model_manager.current_system_prompt)
        if not response:
            response = "抱歉，我无法处理您的请求"
            
        # 添加AI回复到历史
        sessions[session_key].append({"role": "assistant", "content": response})
        
        # 检查是否需要总结并转移到长期记忆
        if len(sessions[session_key]) > SHORT_TERM_MEMORY_LIMIT:
            # 获取前SUMMARY_TRIGGER_SIZE条消息进行总结
            messages_to_summarize = sessions[session_key][:SUMMARY_TRIGGER_SIZE]
            
            # 构建总结提示
            summary_prompt = """请总结以下对话内容，提取关键信息、讨论主题和重要结论。
用简洁的语言概括这段对话的主要内容和结果，不超过150字。"""
            
            try:
                # 调用模型进行总结
                summary = model_manager.call_model(messages_to_summarize, summary_prompt)
                if summary and not summary.startswith("云端模型调用失败") and not summary.startswith("本地模型调用失败"):
                    # 保存到长期记忆
                    long_term_memory.add_memory(session_type, session_key, summary)
                    print(f"已总结对话并保存到长期记忆：{summary[:100]}...")
                    
                    # 从短期记忆中移除已总结的消息
                    sessions[session_key] = sessions[session_key][SUMMARY_TRIGGER_SIZE:]
                else:
                    print("总结失败，保留所有消息")
                    # 如果总结失败，至少保留最新的消息
                    if len(sessions[session_key]) > SHORT_TERM_MEMORY_LIMIT:
                        sessions[session_key] = sessions[session_key][-SHORT_TERM_MEMORY_LIMIT:]
            except Exception as e:
                print(f"总结过程中出错：{e}")
                # 出错时仍保留所有消息，只保留最新的SHORT_TERM_MEMORY_LIMIT条
                if len(sessions[session_key]) > SHORT_TERM_MEMORY_LIMIT:
                    sessions[session_key] = sessions[session_key][-SHORT_TERM_MEMORY_LIMIT:]
        
        # 更新缓存并保存
        if isinstance(event, PrivateMessageEvent):
            session_cache["private"][session_key] = sessions[session_key]
        elif isinstance(event, GroupMessageEvent):
            session_cache["group"][session_key] = sessions[session_key]
        save_sessions()

        await mars_ai.send(response)
    except Exception as e:
        error_msg = f"出错了: {str(e)}"
        await mars_ai.send(error_msg)


