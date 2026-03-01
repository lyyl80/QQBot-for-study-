"""插件配置文件"""

# 平台配置
PLATFORM_CONFIGS = {
    'bilibili': {
        'name': '哔哩哔哩',
        'patterns': [
            r"https?://(?:www\.)?bilibili\.com/video/(BV\w+)[^\s]*",
            r"https?://b23\.tv/\w+[^\s]*",
            r"https?://(?:www\.)?bilibili\.com/video/av\d+[^\s]*",
            r"https?://(?:www\.)?bilibili\.com/bangumi/play/ss\d+[^\s]*",
            r"https?://(?:www\.)?bilibili\.com/bangumi/play/ep\d+[^\s]*",
        ],
        'format_selector': 'bv*+ba/b',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://www.bilibili.com',
        'max_resolution': '720p'
    },
    'youtube': {
        'name': 'YouTube',
        'patterns': [
            r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+",
        ],
        'format_selector': 'bv*+ba/b',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://www.youtube.com',
        'max_resolution': '720p'
    },
    'douyin': {
        'name': '抖音',
        'patterns': [
            r"https?://(?:www\.)?douyin\.com/[^\s]+",
            r"https?://v\.douyin\.com/[^\s]+",
            r"https?://iesdouyin\.com/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15',
        'referer': 'https://www.douyin.com',
        'max_resolution': '720p'
    },
    'xiaohongshu': {
        'name': '小红书',
        'patterns': [
            r"https?://(?:www\.)?xiaohongshu\.com/[^\s]+",
            r"https?://xhslink\.com/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15',
        'referer': 'https://www.xiaohongshu.com',
        'max_resolution': '720p'
    },
    'weibo': {
        'name': '微博',
        'patterns': [
            r"https?://(?:www\.)?weibo\.com/tv/show/[^\s]+",
            r"https?://weibo\.cn/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'referer': 'https://weibo.com',
        'max_resolution': '720p'
    }
}

# 全局设置
GLOBAL_SETTINGS = {
    'cookie_file_path': '~/.yt-dlp/cookies.txt',
    'ffmpeg_path': r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    'timeout': 30,
    'temp_dir_prefix': 'media_dl_'
}

# 错误消息
ERROR_MESSAGES = {
    'no_url_found': '未找到支持的媒体链接',
    'no_file_found': '{platform}下载失败，未找到媒体文件',
    'download_failed': '{platform}下载失败',
    'ffmpeg_missing': '下载失败: FFmpeg处理错误\n提示：请安装FFmpeg或检查其路径配置',
    'login_required': '下载失败: 需要登录或认证',
    'content_protected': '下载失败: 内容受版权保护或需要会员权限',
    'timeout': '下载超时，请稍后重试',
    'generic_error': '下载过程中发生错误: {error}'
}
import re
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from nonebot import on_message, get_plugin
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, GroupMessageEvent, PrivateMessageEvent, Message
from nonebot.rule import Rule
from nonebot.typing import T_State
import yt_dlp
from yt_dlp.utils import DownloadError
from .config import PLATFORM_CONFIGS, GLOBAL_SETTINGS, ERROR_MESSAGES
from .utils import validate_cookies_for_platform, setup_cookies_guide

print("[MEDIA_DOWNLOADER] Media downloader plugin loaded")

@dataclass
class PlatformMatcher:
    """平台URL匹配器"""
    platform: str
    name: str
    patterns: List[str]
    
    def match(self, text: str) -> Optional[str]:
        """匹配文本中的URL"""
        for pattern in self.patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

class MediaDownloader:
    """多媒体下载器主类"""
    
    def __init__(self):
        self.platform_matchers = self._init_platform_matchers()
    
    def _init_platform_matchers(self) -> List[PlatformMatcher]:
        """初始化平台匹配器"""
        matchers = []
        for platform, config in PLATFORM_CONFIGS.items():
            matcher = PlatformMatcher(
                platform=platform,
                name=config['name'],
                patterns=config['patterns']
            )
            matchers.append(matcher)
        return matchers
    
    def extract_media_info(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """从文本中提取媒体信息"""
        for matcher in self.platform_matchers:
            url = matcher.match(text)
            if url:
                return url, matcher.platform, matcher.name
        return None, None, None
    
    def get_ydl_options(self, platform: str, tmpdir: str) -> Dict:
        """获取yt-dlp配置选项"""
        config = PLATFORM_CONFIGS[platform]
        cookie_path = os.path.expanduser(GLOBAL_SETTINGS['cookie_file_path'])
        ffmpeg_path = GLOBAL_SETTINGS['ffmpeg_path']
        
        options = {
            'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
            'format': config['format_selector'],
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'user_agent': config['user_agent'],
            'merge_output_format': 'mp4',
            'format_sort': [f"res:{config.get('max_resolution', '720p').replace('p', '')}", 'ext:mp4:m4a'],
            'ignore_errors': True,
            'no_overwrites': True,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'prefer_ffmpeg': True,
            'socket_timeout': GLOBAL_SETTINGS['timeout'],
        }
        
        # 添加referer
        if config.get('referer'):
            options['referer'] = config['referer']
            
        # 添加cookie文件
        if os.path.exists(cookie_path):
            options['cookiefile'] = cookie_path
            
        # 添加ffmpeg路径
        if os.path.exists(ffmpeg_path):
            options['ffmpeg_location'] = ffmpeg_path
            
        return options

# 初始化下载器实例（移到全局作用域）
downloader = MediaDownloader()

async def handle_download_error(bot: Bot, event: MessageEvent, platform_name: str, error_msg: str):
    """处理下载错误"""
    error_lower = error_msg.lower()
    
    # 根据错误类型返回相应的消息
    if any(keyword in error_lower for keyword in ['ffmpeg', 'merge', 'postprocessing']):
        final_msg = ERROR_MESSAGES['ffmpeg_missing']
    elif 'login' in error_lower or 'authentication' in error_lower:
        final_msg = ERROR_MESSAGES['login_required']
    elif 'copyright' in error_lower or 'protected' in error_lower:
        final_msg = ERROR_MESSAGES['content_protected']
    elif 'timeout' in error_lower:
        final_msg = ERROR_MESSAGES['timeout']
    elif 'cookie' in error_lower or 'fresh' in error_lower or 'access denied' in error_lower:
        final_msg = f"{platform_name}下载失败: 需要更新的Cookies或登录凭证\n{setup_cookies_guide(platform_name)}"
    else:
        final_msg = ERROR_MESSAGES['download_failed'].format(platform=platform_name)
        final_msg += f": {error_msg}"
    
    await media_download.finish(final_msg)

def is_media_link() -> Rule:
    """检查消息是否包含支持的媒体链接"""
    async def _rule(event: MessageEvent, state: T_State) -> bool:
        # 获取文本内容
        plain_text = event.get_plaintext().strip()
        raw_message = str(event.get_message()).strip()
        
        # 使用全局downloader实例
        url, platform, platform_name = downloader.extract_media_info(plain_text)
        if not url:
            url, platform, platform_name = downloader.extract_media_info(raw_message)
        
        if url and platform:
            state["media_url"] = url
            state["platform"] = platform
            state["platform_name"] = platform_name
            return True
            
        return False
    return Rule(_rule)

# 创建消息处理器，优先级设为3（高于AI插件的优先级5）
media_download = on_message(rule=is_media_link(), priority=3, block=True)

@media_download.handle()
async def handle_media_download(bot: Bot, event: MessageEvent, state: T_State):
    """处理媒体下载请求"""
    media_url = state.get("media_url")
    platform = state.get("platform")
    platform_name = state.get("platform_name")
    
    if not media_url or not platform:
        await media_download.finish(ERROR_MESSAGES['no_url_found'])
        return
    
    # 检查是否需要登录凭证
    if not validate_cookies_for_platform(platform):
        needs_login = PLATFORM_CONFIGS[platform].get('needs_login', False)
        if needs_login:
            guide = setup_cookies_guide(platform_name)
            await media_download.send(f"⚠️ {guide}")
    
    # 发送开始下载提示
    await media_download.send(f"检测到{platform_name}链接，开始下载...")
    
    # 创建临时目录
    temp_prefix = GLOBAL_SETTINGS['temp_dir_prefix']
    with tempfile.TemporaryDirectory(prefix=temp_prefix) as tmpdir:
        try:
            # 获取下载配置
            ydl_opts = downloader.get_ydl_options(platform, tmpdir)
            
            # 下载媒体
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
                info = ydl.extract_info(media_url, download=True)
                
                # 查找下载的文件
                video_extensions = ('.mp4', '.flv', '.webm', '.mkv', '.avi', '.mov')
                downloaded_files = [
                    os.path.join(tmpdir, f) 
                    for f in os.listdir(tmpdir) 
                    if f.endswith(video_extensions)
                ]
                
                if not downloaded_files:
                    error_msg = ERROR_MESSAGES['no_file_found'].format(platform=platform_name)
                    await media_download.finish(error_msg)
                    return
                
                video_path = downloaded_files[0]
                video_title = info.get('title', f'未知{platform_name}视频')
                
                # 检查文件大小
                file_size = os.path.getsize(video_path)
                max_size_bytes = 100 * 1024 * 1024  # 100MB
                
                if file_size > max_size_bytes:
                    await media_download.finish(f"{platform_name}文件过大，暂不支持下载")
                    return
                
                # 构建消息
                video_msg = Message(
                    MessageSegment.video(video_path) +
                    MessageSegment.text(f"\n{platform_name}下载完成: {video_title}")
                )
                
                # 发送消息
                if isinstance(event, PrivateMessageEvent):
                    await bot.send_private_msg(user_id=event.user_id, message=video_msg)
                elif isinstance(event, GroupMessageEvent):
                    await bot.send_group_msg(group_id=event.group_id, message=video_msg)
                    
        except DownloadError as e:
            await handle_download_error(bot, event, platform_name, str(e))
        except Exception as e:
            error_msg = ERROR_MESSAGES['generic_error'].format(error=str(e))
            await media_download.finish(error_msg)
