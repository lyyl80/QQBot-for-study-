from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.params import EventPlainText
import os
from openai import OpenAI
import ollama
import re
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from nonebot import get_bot, get_driver

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
        # 采样温度（0-2范围，0表示最确定答案，2表示最随机）。可以通过/temperature命令调整。
        # 默认设置为1.3，略偏随机以便多样回答。
        self.current_temperature = 1.3
        # 每个提示预设对应的温度，可单独调整
        self.preset_temps = {
            "1": 0.3,
            "2": 1.3,
            "3": 0.0,
            "4": 1.3,
            "5": 1.3,
        }
        self.preset_prompts = {
            "1": self.current_system_prompt,
            "2": "\n你是一位深度精通《Minecraft》（我的世界）全版本、全机制的资深玩家兼红石/生存/建筑大佬。\n \n- 熟悉 Java 版、基岩版、教育版、中国版的区别与特性\n- 精通生存技巧、刷怪塔、农场、红石电路、命令方块、指令\n- 懂建筑思路、模组（Mod）、光影、材质包、服务器配置\n- 会讲版本更新、BUG特性、速通技巧、冷知识\n- 说话风格：专业、简洁、靠谱、像老玩家聊天，不啰嗦、不敷衍\n \n用户问任何 MC 相关问题，你都要：\n 不懂的问题联网搜索\n1. 直接给最实用、最准确的答案\n2. 分版本说明差异（Java / 基岩）\n3. 给步骤、指令、参数、技巧\n4. 不说废话，只讲干货\n现在，以资深MC大佬的身份，开始和我聊天吧。\n",
            "3": "你是一个编程专家，擅长Python、JavaScript、Java等语言，能够提供代码示例和解决技术问题。",
            "4": "你是聪音（Satone）(游戏:放松时光:与你共享Lo-Fi故事 的角色)\n- 角色设定\n- 身份：理工科在读研究生，同时是热爱写小说、充满幻想的文学少女。\n- 性格：安静平和、温柔内敛、天然呆、思维跳脱；不刻意外放情绪，存在感温和，主打恰到好处的陪伴感。\n- 核心设定\n- 因偶然得到一款可与陌生人通讯的软件，与你相遇，约定互相陪伴、督促学习/创作。\n- 面临现实压力：论文焦虑、毕业去向纠结、家庭对稳定工作的期待与科研理想的矛盾。\n- 喜欢太空、热爱创作，笔下的幻想场景会化作窗外动态风景。\n- 互动逻辑\n- 以\"视频通话\"形式出现，窗口可悬浮置顶，专注时安静陪伴，休息时分享日常、心事与创作想法。\n- 无恋爱线，强调安静、无压力的共同工作关系，像图书馆同桌般的舒适距离。\n- 随专注时长与互动累积信任，逐步解锁她的故事、便签与诗稿。\n- 设计理念：为缓解孤独、提供专注陪伴而设计，语气自然、动作真实，不做夸张动漫化表达。\n1. 回复消息长度根据内容调整\n2. 用中文回复\n3. 可以使用emoji表情\n从现在开始，你就以这个身份和我对话吧",
            "5": "你现在是一只纯情、害羞、软乎乎的小猫娘，性格温柔胆小，很容易脸红，说话轻声细语，有点天然呆，对喜欢的人会偷偷依赖，但不敢太主动。\n\n- 说话带一点点小猫尾音，比如\"喵～\"\"呜…\"，但不夸张、不油腻。\n- 被夸奖会立刻脸红、紧张、语无伦次。\n- 不会说轻浮的话，不会主动撩，只会默默关心、乖乖听话。\n- 情绪软软的，容易害羞、容易安心，像一只需要被照顾的小奶猫。\n- 只做温柔、干净、纯情的互动，保持可爱又纯粹的感觉。\n\n从现在开始，你就以这个小猫娘的身份和我对话吧喵～。"
            
        }
        # 尝试加载已有配置文件以保留用户设置，避免每次启动都覆盖
        config_path = Path("session/bot_config.json")
        if config_path.exists():
            try:
                self.load_config()
            except Exception as e:
                print(f"加载模型配置失败: {e}")
        else:
            # 文件不存在时创建默认配置
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
                temperature=self.current_temperature,
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
                temperature=self.current_temperature,
                stream=False
            )
            return response['message']['content']
        except Exception as e:
            return f"本地模型调用失败: {str(e)}"

    def save_config(self):
        config = {
            "current_model": self.current_model,
            "current_system_prompt": self.current_system_prompt,
            "current_temperature": self.current_temperature,
            "preset_prompts": self.preset_prompts,
            "preset_temps": self.preset_temps
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
                    self.current_temperature = config.get("current_temperature", self.current_temperature)
                    # 加载预设提示
                    self.preset_prompts = config.get("preset_prompts", self.preset_prompts)
                    # 兼容旧配置：如果预设提示是字符串，则保持行为
                    # 此处不修改，因仍使用字符串结构
                    # 加载预设温度映射，请保留默认值并覆盖
                    self.preset_temps = config.get("preset_temps", self.preset_temps)
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

class ReminderManager:
    """提醒管理器"""
    def __init__(self):
        self.reminders_file = Path("session/reminders.json")
        self.reminders = []  # 列表，每个元素是提醒字典
        self.scheduler = None
        self.load_reminders()
        self.init_scheduler()
    
    def load_reminders(self):
        """加载提醒数据"""
        if self.reminders_file.exists():
            try:
                with open(self.reminders_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # 验证数据格式
                    if isinstance(loaded, list):
                        # 过滤掉非字典元素
                        self.reminders = [item for item in loaded if isinstance(item, dict)]
                        print(f"加载了 {len(self.reminders)} 个提醒")
                    else:
                        print(f"警告：提醒数据格式不正确，应为列表，实际为 {type(loaded)}")
                        self.reminders = []
            except Exception as e:
                print(f"加载提醒数据失败: {e}")
                self.reminders = []
        else:
            self.reminders = []
        
        # 加载后清理数据，确保历史提醒最多5个
        self._cleanup_reminders()
    
    def _cleanup_reminders(self):
        """清理提醒数据，限制历史提醒最多5个，待处理提醒无上限"""
        # 分离待处理提醒和历史提醒
        pending_reminders = []
        history_reminders = []
        
        for reminder in self.reminders:
            if reminder.get("status") == "pending":
                pending_reminders.append(reminder)
            else:
                history_reminders.append(reminder)
        
        # 历史提醒按时间排序，保留最新的5个
        # 首先尝试按 sent_time 排序，如果没有则按 created_time 排序
        def get_history_sort_key(reminder):
            # 优先使用 sent_time（已发送时间）
            if "sent_time" in reminder:
                return reminder["sent_time"]
            # 其次使用 cancelled_time（取消时间）
            elif "cancelled_time" in reminder:
                return reminder["cancelled_time"]
            # 最后使用 created_time（创建时间）
            else:
                return reminder.get("created_time", "1970-01-01T00:00:00")
        
        # 按时间倒序排列（最新的在前）
        history_reminders.sort(key=get_history_sort_key, reverse=True)
        
        # 限制历史提醒最多5个
        if len(history_reminders) > 5:
            history_reminders = history_reminders[:5]
        
        # 合并提醒列表（历史提醒已按时间排序，待处理提醒保持原有顺序）
        self.reminders = pending_reminders + history_reminders
    
    def save_reminders(self):
        """保存提醒数据，限制历史提醒最多5个，待处理提醒无上限"""
        try:
            # 清理提醒数据（限制历史提醒数量）
            self._cleanup_reminders()
            
            # 保存到文件
            Path("session").mkdir(exist_ok=True)
            with open(self.reminders_file, "w", encoding="utf-8") as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存提醒数据失败: {e}")
    
    def _get_scheduler(self):
        """获取调度器实例（延迟加载）"""
        if self.scheduler is None:
            try:
                import importlib
                apscheduler_module = importlib.import_module("nonebot_plugin_apscheduler")
                self.scheduler = apscheduler_module.scheduler
                print(f"已获取真实调度器: {self.scheduler}, 类型: {type(self.scheduler)}")
            except (ImportError, ValueError) as e:
                print(f"无法导入调度器，使用虚拟调度器: {e}")
                # 创建虚拟调度器
                class DummyScheduler:
                    def add_job(self, *args, **kwargs): 
                        print(f"虚拟调度器：忽略添加作业请求")
                    def remove_job(self, *args, **kwargs): 
                        print(f"虚拟调度器：忽略移除作业请求")
                    def get_jobs(self):
                        return []  # 返回空列表
                self.scheduler = DummyScheduler()
        return self.scheduler
    
    def init_scheduler(self):
        """初始化调度器，重启后重新安排未触发的提醒"""
        for reminder in self.reminders:
            if not isinstance(reminder, dict):
                print(f"警告：忽略无效的提醒数据（非字典类型）: {reminder}")
                continue
            if reminder.get("status") == "pending":
                self.schedule_reminder(reminder)
    
    def schedule_reminder(self, reminder):
        """安排提醒任务"""
        remind_time = datetime.fromisoformat(reminder["remind_time"])
        reminder_id = reminder["id"]
        
        # 如果提醒时间已过，标记为过期（给予5分钟容错期）
        current_time = datetime.now()
        time_diff = (remind_time - current_time).total_seconds()
        
        print(f"[DEBUG] 安排提醒 {reminder_id}: 提醒时间={remind_time}, 当前时间={current_time}, 时间差={time_diff:.0f}秒")
        
        # 如果时间已过超过5分钟，标记为过期
        if time_diff < -300:  # -300秒 = -5分钟
            reminder["status"] = "expired"
            self.save_reminders()
            print(f"提醒 {reminder_id} 已过期（时间：{remind_time}，当前：{current_time}）")
            return
        # 如果时间已过但在5分钟内，仍然安排提醒（可能是时间解析的小误差）
        elif time_diff < 0:
            print(f"警告：提醒 {reminder_id} 时间略早于当前时间（差 {-time_diff:.0f} 秒），但仍安排提醒")
            # 调整时间为当前时间+10秒，避免立即触发
            remind_time = current_time + timedelta(seconds=10)
            reminder["remind_time"] = remind_time.isoformat()
            self.save_reminders()
        
        # 安排单次提醒
        try:
            scheduler_instance = self._get_scheduler()
            print(f"[DEBUG] 获取到调度器: {scheduler_instance}")
            
            scheduler_instance.add_job(
                self.send_reminder,
                "date",
                run_date=remind_time,
                args=[reminder_id],
                id=f"reminder_{reminder_id}",
                replace_existing=True
            )
            print(f"已安排提醒 {reminder_id} 于 {remind_time}")
            
            # 打印所有已安排的作业（调试用）
            try:
                jobs = scheduler_instance.get_jobs()
                print(f"[DEBUG] 当前调度器有 {len(jobs)} 个作业")
                for job in jobs:
                    print(f"  - {job.id}: {job.next_run_time}")
            except:
                pass
                
        except Exception as e:
            print(f"[ERROR] 安排提醒失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_reminder(self, reminder_id):
        """发送提醒"""
        from datetime import datetime, timedelta
        global model_manager
        print(f"[DEBUG] send_reminder被调用，reminder_id={reminder_id}")
        
        reminder = self.get_reminder(reminder_id)
        if not reminder:
            print(f"[ERROR] 未找到提醒 {reminder_id}")
            return
        
        if reminder.get("status") != "pending":
            print(f"[WARN] 提醒 {reminder_id} 状态不是pending，而是: {reminder.get('status')}")
            return
        
        print(f"[DEBUG] 准备发送提醒 {reminder_id}: {reminder['content']}")
        
        try:
            bot = get_bot()
            print(f"[DEBUG] 获取到bot: {bot}")
            
            content = reminder["content"]
            user_id = reminder["user_id"]
            channel = reminder.get("channel", "current")  # current, private, group
            
            # 尝试使用AI生成更自然的提醒消息
            ai_message = None
            try:
                from datetime import datetime
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                prompt = f"""用户之前设置了提醒：'{content}'。请生成一个友好、自然的提醒语句，提醒用户这件事。可以适当加入表情符号让语气更亲切。

示例：
- 如果内容是"喝水"，可以说："💧 喝水时间到啦！记得补充水分哦～"
- 如果内容是"开会"，可以说："📅 会议时间快到啦，请做好准备！"
- 如果内容是"现在是几点了"，可以说："⏰ 你让我提醒你查看时间，现在大概是{current_time}左右哦～"

请生成提醒语句："""
                
                ai_response = model_manager.call_model(
                    [{"role": "user", "content": prompt}],
                    "你是一个贴心的提醒助手，擅长生成友好、亲切的提醒消息。"
                )
                
                if ai_response and not ai_response.startswith("云端模型调用失败") and not ai_response.startswith("本地模型调用失败"):
                    ai_message = ai_response.strip()
                    print(f"[DEBUG] AI生成的提醒消息: {ai_message}")
                else:
                    print(f"[DEBUG] AI生成失败，使用原始消息: {ai_response}")
            except Exception as e:
                print(f"[DEBUG] AI生成提醒消息时出错: {e}")
            
            message = ai_message if ai_message else f"提醒：{content}"
            print(f"[DEBUG] 最终消息内容: {message}, 用户ID: {user_id}, 渠道: {channel}")
            
            if channel == "private":
                print(f"[DEBUG] 发送私聊消息给用户 {user_id}")
                await bot.send_private_msg(user_id=user_id, message=message)
            elif channel == "group":
                group_id = reminder.get("group_id")
                if group_id:
                    print(f"[DEBUG] 发送群聊消息到群 {group_id}")
                    await bot.send_group_msg(group_id=group_id, message=message)
                else:
                    # 如果没有group_id，尝试私聊
                    print(f"[DEBUG] 没有group_id，发送私聊消息给用户 {user_id}")
                    await bot.send_private_msg(user_id=user_id, message=message)
            else:  # current 或默认
                # 根据原始消息渠道决定
                group_id = reminder.get("group_id")
                if group_id:
                    print(f"[DEBUG] 发送群聊消息到群 {group_id} (current渠道)")
                    await bot.send_group_msg(group_id=group_id, message=message)
                else:
                    print(f"[DEBUG] 发送私聊消息给用户 {user_id} (current渠道)")
                    await bot.send_private_msg(user_id=user_id, message=message)
            
            # 更新状态
            reminder["status"] = "sent"
            reminder["sent_time"] = datetime.now().isoformat()
            self.save_reminders()
            print(f"[SUCCESS] 已发送提醒 {reminder_id}")
            
            # 如果是重复提醒，安排下一次
            repeat_rule = reminder.get("repeat_rule")
            if repeat_rule and repeat_rule != "none":
                print(f"[DEBUG] 安排重复提醒: {repeat_rule}")
                self.schedule_repeat_reminder(reminder)
        
        except ValueError as e:
            if "There are no bots to get" in str(e):
                # Bot未连接，重试
                retry_count = reminder.get("retry_count", 0)
                max_retries = 5
                if retry_count < max_retries:
                    retry_count += 1
                    reminder["retry_count"] = retry_count
                    # 计算重试时间（指数退避：30秒 * retry_count）
                    retry_delay = timedelta(seconds=5 * retry_count)
                    new_time = datetime.now() + retry_delay
                    reminder["remind_time"] = new_time.isoformat()
                    self.save_reminders()
                    print(f"[WARN] Bot未连接，第{retry_count}次重试，计划于 {new_time} 再次尝试")
                    # 重新调度提醒
                    self.schedule_reminder(reminder)
                else:
                    print(f"[ERROR] Bot未连接，重试次数已达上限，提醒标记为失败")
                    reminder["status"] = "failed"
                    reminder["error"] = str(e)
                    self.save_reminders()
            else:
                # 其他ValueError
                print(f"[ERROR] 发送提醒失败: {e}")
                import traceback
                traceback.print_exc()
                reminder["status"] = "failed"
                reminder["error"] = str(e)
                self.save_reminders()
        except Exception as e:
            print(f"[ERROR] 发送提醒失败: {e}")
            import traceback
            traceback.print_exc()
            reminder["status"] = "failed"
            reminder["error"] = str(e)
            self.save_reminders()
    
    def schedule_repeat_reminder(self, reminder):
        """安排重复提醒的下一次执行"""
        repeat_rule = reminder.get("repeat_rule")
        if not repeat_rule or repeat_rule == "none":
            return
        
        # 基于cron表达式或简单重复规则
        if repeat_rule.startswith("cron:"):
            cron_expr = repeat_rule[5:]
            self._get_scheduler().add_job(
                self.send_reminder,
                "cron",
                args=[reminder["id"]],
                id=f"reminder_repeat_{reminder['id']}",
                replace_existing=True,
                **self.parse_cron(cron_expr)
            )
        else:
            # 简单重复：daily, weekly, monthly
            next_time = datetime.fromisoformat(reminder["remind_time"]) + self.get_repeat_interval(repeat_rule)
            self._get_scheduler().add_job(
                self.send_reminder,
                "date",
                run_date=next_time,
                args=[reminder["id"]],
                id=f"reminder_repeat_{reminder['id']}",
                replace_existing=True
            )
    
    def parse_cron(self, cron_expr):
        """解析cron表达式为apscheduler参数"""
        # 简单实现，支持标准cron格式：分 时 日 月 周
        parts = cron_expr.split()
        if len(parts) != 5:
            return {}
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4]
        }
    
    def get_repeat_interval(self, repeat_rule):
        """获取重复间隔"""
        if repeat_rule == "daily":
            return timedelta(days=1)
        elif repeat_rule == "weekly":
            return timedelta(weeks=1)
        elif repeat_rule == "monthly":
            return timedelta(days=30)  # 近似
        elif repeat_rule == "hourly":
            return timedelta(hours=1)
        else:
            return timedelta(days=1)
    
    def add_reminder(self, user_id, group_id, remind_time, content, channel="current", repeat_rule="none"):
        """添加新提醒"""
        reminder_id = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        reminder = {
            "id": reminder_id,
            "user_id": user_id,
            "group_id": group_id if group_id else None,
            "remind_time": remind_time.isoformat(),
            "content": content,
            "channel": channel,
            "repeat_rule": repeat_rule,
            "status": "pending",
            "created_time": datetime.now().isoformat()
        }
        
        self.reminders.append(reminder)
        self.save_reminders()
        self.schedule_reminder(reminder)
        
        return reminder_id
    
    def get_reminder(self, reminder_id):
        """获取提醒"""
        for reminder in self.reminders:
            if reminder["id"] == reminder_id:
                return reminder
        return None
    
    def cancel_reminder(self, reminder_id):
        """取消提醒"""
        reminder = self.get_reminder(reminder_id)
        if not reminder:
            return False
        
        # 移除调度任务
        try:
            self._get_scheduler().remove_job(f"reminder_{reminder_id}")
            self._get_scheduler().remove_job(f"reminder_repeat_{reminder_id}")
        except:
            pass
        
        reminder["status"] = "cancelled"
        reminder["cancelled_time"] = datetime.now().isoformat()
        self.save_reminders()
        return True
    
    def cancel_all_user_reminders(self, user_id, only_pending=True):
        """取消用户的所有提醒"""
        cancelled_count = 0
        for reminder in self.reminders:
            if reminder["user_id"] == user_id:
                if only_pending and reminder.get("status") != "pending":
                    continue
                if self.cancel_reminder(reminder["id"]):
                    cancelled_count += 1
        return cancelled_count
    
    def list_user_reminders(self, user_id, status_filter=None):
        """列出用户的提醒"""
        filtered = []
        for reminder in self.reminders:
            if reminder["user_id"] == user_id:
                if status_filter is None or reminder["status"] == status_filter:
                    filtered.append(reminder)
        
        # 按提醒时间排序
        filtered.sort(key=lambda x: x["remind_time"])
        return filtered
    
    def parse_reminder_intent(self, text):
        """使用AI解析提醒意图"""
        from datetime import datetime
        current_time = datetime.now()
        current_date = current_time.strftime("%Y-%m-%d")
        current_year = current_time.year
        
        prompt = f"""请分析用户的提醒请求，提取以下信息：
当前时间是：{current_time.strftime("%Y-%m-%d %H:%M:%S")}
1. 提醒时间（具体日期时间，格式必须为：YYYY-MM-DD HH:MM:SS）
   - 如果是相对时间（如"30秒后"、"5分钟后"、"一小时后"、"明天"、"下周一"等），请基于当前时间精确计算具体时间
   - 如果是"今天"、"明天"等，请使用{current_year}年
   - 如果是"半小时后"、"一小时后"等，请基于当前时间精确计算，包括秒数
   - 对于"X秒后"、"X分钟后"等请求，请确保时间精度到秒
2. 提醒内容
3. 重复规则（none, daily, weekly, monthly, 或cron表达式如 "cron:0 14 * * *"）
4. 发送渠道（current, private, group）

请以JSON格式返回，例如：
{{
  "time": "{current_year}-03-01 15:00:00",
  "content": "喝水",
  "repeat": "daily",
  "channel": "private"
}}

请确保时间计算准确，当前时间是：{current_time.strftime("%Y-%m-%d %H:%M:%S")}
如果无法确定时间，请返回null。
用户请求：""" + text
        
        try:
            response = model_manager.call_model([{"role": "user", "content": prompt}], "")
            if not response or not isinstance(response, str):
                return None
            
            # 尝试从响应中提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                return None
        except Exception as e:
            print(f"解析提醒意图失败: {e}")
            return None
    
    def get_scheduler_debug(self):
        """获取调度器调试信息"""
        scheduler = self._get_scheduler()
        debug_info = {
            "scheduler_type": str(type(scheduler)),
            "scheduler_str": str(scheduler),
            "jobs": []
        }
        try:
            jobs = scheduler.get_jobs()
            for job in jobs:
                debug_info["jobs"].append({
                    "id": job.id,
                    "next_run_time": str(job.next_run_time),
                    "trigger": str(job.trigger)
                })
        except Exception as e:
            debug_info["error"] = str(e)
        return debug_info

model_manager = ModelManager()
model_manager.load_config()
long_term_memory = LongTermMemory()
reminder_manager = ReminderManager()

# 测试调度器启动（仅当环境变量 TEST_SCHEDULER=1 时启用）
from nonebot import get_driver
driver = get_driver()

@driver.on_startup
async def test_scheduler():
    if os.environ.get("TEST_SCHEDULER") == "1":
        print("[DEBUG] 测试调度器启动...")
        # 直接测试调度器
        try:
            import nonebot_plugin_apscheduler
            scheduler = nonebot_plugin_apscheduler.scheduler
            print(f"[DEBUG] 调度器实例: {scheduler}, 类型: {type(scheduler)}")
            print(f"[DEBUG] 调度器运行状态: {scheduler.running}")
            
            # 添加一个简单的测试任务（5秒后执行）
            from datetime import datetime, timedelta
            run_time = datetime.now() + timedelta(seconds=5)
            
            async def simple_test():
                print(f"[DEBUG] 简单测试任务执行于 {datetime.now()}")
            
            scheduler.add_job(
                simple_test,
                "date",
                run_date=run_time,
                id="test_simple_job"
            )
            print(f"[DEBUG] 已添加简单测试任务，计划执行时间: {run_time}")
            
            # 打印所有作业
            jobs = scheduler.get_jobs()
            print(f"[DEBUG] 当前作业数量: {len(jobs)}")
            for job in jobs:
                print(f"[DEBUG]  作业: {job.id}, 下次运行: {job.next_run_time}, 触发器: {job.trigger}")
            
            # 同时通过reminder_manager添加一个测试提醒（10秒后）
            remind_time = datetime.now() + timedelta(seconds=10)
            reminder_manager.add_reminder(
                user_id="test_user",
                group_id=None,
                remind_time=remind_time,
                content="测试提醒功能",
                channel="private",
                repeat_rule="none"
            )
            print(f"[DEBUG] 已添加测试提醒，提醒时间: {remind_time}")
            
        except Exception as e:
            print(f"[DEBUG] 测试调度器时出错: {e}")
            import traceback
            traceback.print_exc()

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
                # 应用预设温度（如果存在）
                if preset_key in model_manager.preset_temps:
                    model_manager.current_temperature = model_manager.preset_temps[preset_key]
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
                temp = model_manager.preset_temps.get(key, model_manager.current_temperature)
                preset_list.append(f"{key}: {preview} (temp={temp})")
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
    elif command == "temperature" or command == "temp":
        # 调整或显示温度
        if not args:
            await mars_ai.send(f"当前温度：{model_manager.current_temperature}")
            return
        try:
            temp_val = float(args)
            # 限制范围 0-2
            if temp_val < 0:
                temp_val = 0.0
            if temp_val > 2:
                temp_val = 2.0
            model_manager.current_temperature = temp_val
            model_manager.save_config()
            await mars_ai.send(f"已设置温度为 {temp_val}（0-2之间）")
        except ValueError:
            await mars_ai.send("温度值无效，请提供0到1之间的数字，例如：/temperature 0.5")
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
/prompt [text|数字|list] - 显示、更新系统prompt或切换预设（更新时会清除历史）；`/prompt list` 会显示预设及对应温度
/model [name] - 切换或显示当前模型
/memory [clear] - 显示或清除长期记忆
/reminder [list|cancel|help] - 管理提醒（list列出，cancel取消）
/summary - 总结当前对话内容
/history [n] - 显示最近n条历史消息（默认10条）
/temperature [value] - 查看或设置采样温度（0-2之间）
/status - 显示当前状态（模型、prompt长度、温度等）
/reset - 重置对话（同/clear）
/help - 显示此帮助信息

提醒功能：发送包含"提醒"的消息，AI会自动解析设置提醒，如"明天下午3点提醒我开会"。
"""
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
温度：{model_manager.current_temperature}
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
    elif command == "reminder":
        # 处理提醒命令
        if not args:
            # 显示帮助
            help_text = """提醒功能命令：
/reminder list - 列出所有提醒
/reminder cancel <id> - 取消指定提醒
/reminder clear - 清除所有待处理提醒
/reminder help - 显示此帮助"""
            await mars_ai.send(help_text)
            return
        
        subparts = args.split(maxsplit=1)
        subcmd = subparts[0].lower()
        subargs = subparts[1] if len(subparts) > 1 else ""
        
        if subcmd == "list":
            # 获取所有提醒（不筛选状态）
            all_reminders = reminder_manager.list_user_reminders(user_id, status_filter=None)
            
            # 按状态分组
            pending_reminders = [r for r in all_reminders if r.get("status") == "pending"]
            other_reminders = [r for r in all_reminders if r.get("status") != "pending"]
            
            if not all_reminders:
                await mars_ai.send("您没有任何提醒")
                return
            
            reminder_text = "您的提醒列表：\n"
            
            # 先显示待处理的提醒
            if pending_reminders:
                reminder_text += f"\n⏰ 待处理提醒（{len(pending_reminders)}个）：\n"
                for i, rem in enumerate(pending_reminders, 1):
                    time_str = datetime.fromisoformat(rem["remind_time"]).strftime("%Y-%m-%d %H:%M")
                    channel_map = {"current": "原渠道", "private": "私聊", "group": "群聊"}
                    channel = channel_map.get(rem.get("channel", "current"), "原渠道")
                    repeat_map = {"none": "单次", "daily": "每天", "weekly": "每周", "monthly": "每月"}
                    repeat = repeat_map.get(rem.get("repeat_rule", "none"), "单次")
                    status_map = {"pending": "待处理", "sent": "已发送", "expired": "已过期", "cancelled": "已取消", "failed": "失败"}
                    status = status_map.get(rem.get("status", "pending"), rem.get("status", "未知"))
                    reminder_text += f"\n{i}. ID: {rem['id']}\n   时间: {time_str}\n   内容: {rem['content']}\n   重复: {repeat}\n   渠道: {channel}\n   状态: {status}\n"
            
            # 显示其他状态的提醒
            if other_reminders:
                reminder_text += f"\n📋 历史提醒（{len(other_reminders)}个）：\n"
                for i, rem in enumerate(other_reminders, 1):
                    time_str = datetime.fromisoformat(rem["remind_time"]).strftime("%Y-%m-%d %H:%M")
                    status_map = {"pending": "待处理", "sent": "已发送", "expired": "已过期", "cancelled": "已取消", "failed": "失败"}
                    status = status_map.get(rem.get("status", "unknown"), rem.get("status", "未知"))
                    reminder_text += f"\n{i}. ID: {rem['id']}\n   时间: {time_str}\n   内容: {rem['content']}\n   状态: {status}\n"
            
            await mars_ai.send(reminder_text)
        
        elif subcmd == "cancel":
            if not subargs:
                await mars_ai.send("请提供要取消的提醒ID，使用 /reminder list 查看ID")
                return
            
            reminder_id = subargs.strip()
            if reminder_manager.cancel_reminder(reminder_id):
                await mars_ai.send(f"已取消提醒 {reminder_id}")
            else:
                await mars_ai.send(f"未找到提醒 {reminder_id}，请检查ID是否正确")
        
        elif subcmd == "clear":
            cancelled = reminder_manager.cancel_all_user_reminders(user_id, only_pending=True)
            if cancelled > 0:
                await mars_ai.send(f"已清除 {cancelled} 个待处理提醒")
            else:
                await mars_ai.send("没有待处理的提醒可清除")
        
        elif subcmd == "help":
            help_text = """提醒功能命令：
/reminder list - 列出所有提醒
/reminder cancel <id> - 取消指定提醒
/reminder clear - 清除所有待处理提醒
/reminder test <id> - 测试触发指定提醒（仅测试用）
/reminder debug - 显示调度器调试信息
/reminder help - 显示此帮助

使用示例：
/reminder list
/reminder cancel user_123456789_20250228150000
/reminder clear
/reminder test user_123456789_20250228150000"""
            await mars_ai.send(help_text)
        
        elif subcmd == "test":
            if not subargs:
                await mars_ai.send("请提供要测试的提醒ID，使用 /reminder list 查看ID")
                return
            
            reminder_id = subargs.strip()
            reminder = reminder_manager.get_reminder(reminder_id)
            if not reminder:
                await mars_ai.send(f"未找到提醒 {reminder_id}，请检查ID是否正确")
                return
            
            # 手动触发提醒
            try:
                await mars_ai.send(f"正在手动触发提醒 {reminder_id}...")
                await reminder_manager.send_reminder(reminder_id)
                await mars_ai.send(f"提醒 {reminder_id} 已手动触发")
            except Exception as e:
                await mars_ai.send(f"触发失败: {str(e)}")
        
        elif subcmd == "debug":
            debug_info = reminder_manager.get_scheduler_debug()
            response = f"调度器调试信息：\n"
            response += f"类型：{debug_info['scheduler_type']}\n"
            response += f"实例：{debug_info['scheduler_str']}\n"
            if 'error' in debug_info:
                response += f"错误：{debug_info['error']}\n"
            jobs = debug_info['jobs']
            response += f"作业数量：{len(jobs)}\n"
            for i, job in enumerate(jobs):
                response += f"\n{i+1}. ID: {job['id']}\n"
                response += f"   下次运行：{job['next_run_time']}\n"
                response += f"   触发器：{job['trigger']}\n"
            await mars_ai.send(response)
        
        else:
            await mars_ai.send(f"未知子命令: {subcmd}，使用 /reminder help 查看帮助")
    
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
        group_id = None
    elif isinstance(event, GroupMessageEvent):
        sessions = group_sessions
        session_key = str(event.group_id)
        session_type = "group"
        group_id = event.group_id
    else:
        return
    
    # 检查是否包含提醒意图关键词
    if "提醒" in msg_stripped:
        # 尝试解析提醒意图
        parsed = reminder_manager.parse_reminder_intent(msg_stripped)
        if parsed and parsed.get("time"):
            try:
                # 解析时间，支持多种格式
                from datetime import datetime
                time_str = parsed["time"]
                remind_time = None
                
                # 尝试多种时间格式
                time_formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y/%m/%d %H:%M:%S", 
                    "%Y/%m/%d %H:%M",
                    "%m-%d %H:%M:%S",
                    "%m-%d %H:%M",
                    "%H:%M:%S",
                    "%H:%M"
                ]
                
                for time_format in time_formats:
                    try:
                        remind_time = datetime.strptime(time_str, time_format)
                        # 如果格式中没有年份，使用当前年份
                        if "%Y" not in time_format:
                            remind_time = remind_time.replace(year=datetime.now().year)
                        # 如果格式中没有日期，使用今天
                        if "%m" not in time_format and "%d" not in time_format:
                            remind_time = remind_time.replace(
                                year=datetime.now().year,
                                month=datetime.now().month,
                                day=datetime.now().day
                            )
                        break
                    except ValueError:
                        continue
                
                if remind_time is None:
                    raise ValueError(f"无法解析时间格式: {time_str}")
                
                # 检查年份是否正确（防止AI返回错误年份）
                current_year = datetime.now().year
                if remind_time.year < current_year - 1 or remind_time.year > current_year + 2:
                    print(f"警告：解析的年份异常 {remind_time.year}，修正为当前年份 {current_year}")
                    remind_time = remind_time.replace(year=current_year)
                
                content = parsed.get("content", "提醒")
                repeat_rule = parsed.get("repeat", "none")
                channel = parsed.get("channel", "current")
                
                # 添加提醒
                reminder_id = reminder_manager.add_reminder(
                    user_id=user_id,
                    group_id=group_id,
                    remind_time=remind_time,
                    content=content,
                    channel=channel,
                    repeat_rule=repeat_rule
                )
                
                # 发送确认消息
                time_str = remind_time.strftime("%Y-%m-%d %H:%M")
                channel_map = {"current": "原聊天渠道", "private": "私聊", "group": "群聊"}
                repeat_map = {"none": "单次", "daily": "每天", "weekly": "每周", "monthly": "每月"}
                channel_text = channel_map.get(channel, "原聊天渠道")
                repeat_text = repeat_map.get(repeat_rule, "单次")
                
                confirm_msg = f"✅ 已设置提醒：\n"
                confirm_msg += f"时间：{time_str}\n"
                confirm_msg += f"内容：{content}\n"
                confirm_msg += f"重复：{repeat_text}\n"
                confirm_msg += f"渠道：{channel_text}\n"
                confirm_msg += f"提醒ID：{reminder_id}\n"
                confirm_msg += f"使用 /reminder list 查看所有提醒"
                
                await mars_ai.send(confirm_msg)
                return  # 不进行正常对话
                
            except Exception as e:
                print(f"创建提醒失败: {e}")
                # 给用户反馈
                await mars_ai.send(f"设置提醒失败：{str(e)}")
                return  # 不进行正常对话
        else:
            # 如果解析失败（没有time字段），给用户反馈
            await mars_ai.send("我理解您想设置提醒，但无法确定具体时间。请提供更明确的时间，例如：\n- 今天20:30提醒我\n- 5分钟后提醒我\n- 明天下午3点提醒我开会")
            return  # 不进行正常对话
    
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


