import re
import asyncio
import tempfile
import os
from pathlib import Path
from nonebot import on_message, get_plugin
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, GroupMessageEvent, PrivateMessageEvent, Message
from nonebot.rule import Rule
from nonebot.typing import T_State
import yt_dlp
from yt_dlp.utils import DownloadError

print("[BILI_PLUGIN] Bilibili downloader plugin loaded")  

# B站链接正则表达式
BILIBILI_PATTERNS = [
    r"https?://(?:www\.)?bilibili\.com/video/(BV\w+)[^\s]*",
    r"https?://b23\.tv/\w+[^\s]*",
    r"https?://(?:www\.)?bilibili\.com/video/av\d+[^\s]*",
    r"https?://(?:www\.)?bilibili\.com/bangumi/play/ss\d+[^\s]*",
    r"https?://(?:www\.)?bilibili\.com/bangumi/play/ep\d+[^\s]*",
]
def extract_bilibili_url(text: str) -> str | None:
    """从文本中提取第一个B站视频链接"""
    for pattern in BILIBILI_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

def is_bilibili_link() -> Rule:
    """检查消息是否包含B站链接"""
    async def _rule(event: MessageEvent, state: T_State) -> bool:
        # 多种方式获取文本
        plain_text = event.get_plaintext().strip()
        raw_message = str(event.get_message()).strip()
        print(f"[BILI_DEBUG] Event type: {type(event).__name__}")
        print(f"[BILI_DEBUG] Plain text: {plain_text}")
        print(f"[BILI_DEBUG] Raw message: {raw_message}")
        
        # 尝试从纯文本匹配
        url = extract_bilibili_url(plain_text)
        if not url:
            # 如果纯文本没匹配，尝试原始消息
            url = extract_bilibili_url(raw_message)
        
        print(f"[BILI_DEBUG] Extracted URL: {url}")
        if url:
            state["video_url"] = url
            return True
        
        print(f"[BILI_DEBUG] No Bilibili URL found")
        return False
    return Rule(_rule)

# 创建消息处理器，优先级设为10（高于其他插件）
bili_download = on_message(rule=is_bilibili_link(), priority=10, block=True)

@bili_download.handle()
async def handle_bilibili(bot: Bot, event: MessageEvent, state: T_State):
    print(f"[BILI_DEBUG] Handler called, video_url: {state.get('video_url')}")
    video_url = state.get("video_url")
    
    if not video_url:
        await bili_download.finish()
        return
    
    # 发送正在下载的提示
    await bili_download.send(f"检测到B站视频链接，开始下载...")
    
    # 创建临时目录存放下载的视频
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
            'format': 'bv*+ba/b',  # B站专用格式选择器
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': 'https://www.bilibili.com',
            'cookiefile': os.path.join(Path.home(), '.yt-dlp', 'cookies.txt') if os.path.exists(os.path.join(Path.home(), '.yt-dlp', 'cookies.txt')) else None,
            'merge_output_format': 'mp4',
            'format_sort': ['res:720', 'ext:mp4:m4a'],  # 优先720p和mp4格式
            'ignore_errors': True,
            'no_overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'prefer_ffmpeg': True,
        }
        
        try:
            # 下载视频
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
                info = ydl.extract_info(video_url, download=True)
                downloaded_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(('.mp4', '.flv', '.webm', '.mkv'))]
                if not downloaded_files:
                    await bili_download.finish("下载失败，未找到视频文件")
                    return
                
                video_path = downloaded_files[0]
                video_title = info.get('title', '未知标题')
                
                # 构建消息：视频 + 文本说明
                video_msg = Message(
                    MessageSegment.video(video_path) +
                    MessageSegment.text(f"\n视频下载完成: {video_title}")
                )
                
                # 发送消息
                if isinstance(event, PrivateMessageEvent):
                    # 私聊发送文件
                    await bot.send_private_msg(
                        user_id=event.user_id,
                        message=video_msg
                    )
                elif isinstance(event, GroupMessageEvent):
                    # 群聊发送文件
                    await bot.send_group_msg(
                        group_id=event.group_id,
                        message=video_msg
                    )
                
                # 不再需要单独发送finish消息
                
        except DownloadError as e:
            print(f"[BILI_DEBUG] DownloadError: {e}")
            
            # 检查错误是否与FFmpeg相关
            error_msg = str(e)
            if 'ffmpeg' in error_msg.lower() or 'merge' in error_msg.lower():
                # FFmpeg不可用，尝试下载视频格式（无音频）
                print(f"[BILI_DEBUG] FFmpeg issue detected, trying video-only formats...")
                try:
                    # 尝试获取视频信息
                    with yt_dlp.YoutubeDL({
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'referer': 'https://www.bilibili.com',
                    }) as ydl_info:  # type: ignore
                        info = ydl_info.extract_info(video_url, download=False)
                        
                        if info and 'formats' in info:
                            formats = info['formats']
                            if formats:
                                # 寻找视频格式（非音频）
                                video_formats = []
                                for f in formats:
                                    vcodec = f.get('vcodec', 'none')
                                    if vcodec != 'none':  # 有视频编码
                                        video_formats.append(f)
                                
                                # 尝试下载第一个视频格式
                                if video_formats:
                                    video_format = video_formats[0]
                                    format_id = video_format.get('format_id')
                                    print(f"[BILI_DEBUG] Trying video-only format: {format_id}")
                                    
                                    with yt_dlp.YoutubeDL({
                                        'format': format_id,
                                        'outtmpl': os.path.join(tmpdir, '%(title)s_video.%(ext)s'),
                                        'quiet': True,
                                        'no_warnings': True,
                                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                        'referer': 'https://www.bilibili.com',
                                    }) as ydl_video:  # type: ignore
                                        ydl_video.extract_info(video_url, download=True)
                                        
                                        # 查找下载的文件
                                        downloaded_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(('.mp4', '.flv', '.webm', '.mkv'))]
                                        if downloaded_files:
                                            video_path = downloaded_files[0]
                                            video_title = info.get('title', '未知标题')
                                            # 构建消息：视频 + 文本说明
                                            video_msg = Message(
                                                MessageSegment.video(video_path) +
                                                MessageSegment.text(f"\n视频下载完成 (无音频，需要安装FFmpeg): {video_title}\n提示：安装FFmpeg后可下载完整带音频视频")
                                            )
                                            
                                            if isinstance(event, PrivateMessageEvent):
                                                await bot.send_private_msg(user_id=event.user_id, message=video_msg)
                                            elif isinstance(event, GroupMessageEvent):
                                                await bot.send_group_msg(group_id=event.group_id, message=video_msg)
                                            return
                except Exception as video_error:
                    print(f"[BILI_DEBUG] Video-only download also failed: {video_error}")
            
            # 通用错误消息
            await bili_download.finish(f"下载失败: {error_msg}\n可能需要安装FFmpeg或B站会员")
        except Exception as e:
            await bili_download.finish(f"发生错误: {str(e)}")