"""多媒体下载器配置文件"""

# 支持的平台配置
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
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.bilibili.com',
        'needs_login': False,
        'max_resolution': '1080p'
    },
    'youtube': {
        'name': 'YouTube',
        'patterns': [
            r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+",
        ],
        'format_selector': 'bv*+ba/b',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.youtube.com',
        'needs_login': False,
        'max_resolution': '1080p'
    },
    'douyin': {
        'name': '抖音',
        'patterns': [
            r"https?://(?:www\.)?douyin\.com/[^\s]+",
            r"https?://v\.douyin\.com/[^\s]+",
            r"https?://iesdouyin\.com/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.douyin.com',
        'needs_login': True,
        'max_resolution': '720p'
    },
    'xiaohongshu': {
        'name': '小红书',
        'patterns': [
            r"https?://(?:www\.)?xiaohongshu\.com/[^\s]+",
            r"https?://xhslink\.com/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.xiaohongshu.com',
        'needs_login': True,
        'max_resolution': '720p'
    },
    'weibo': {
        'name': '微博',
        'patterns': [
            r"https?://(?:www\.)?weibo\.com/tv/show/[^\s]+",
            r"https?://weibo\.cn/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://weibo.com',
        'needs_login': False,
        'max_resolution': '720p'
    },
    'tiktok': {
        'name': 'TikTok',
        'patterns': [
            r"https?://(?:www\.)?tiktok\.com/@[^\s]+",
            r"https?://vm\.tiktok\.com/[^\s]+",
        ],
        'format_selector': 'bv*[height<=720]+ba/bv*[height<=720]+ba',
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.tiktok.com',
        'needs_login': False,
        'max_resolution': '720p'
    }
}

# 全局设置
GLOBAL_SETTINGS = {
    'temp_dir_prefix': 'media_download_',
    'default_max_file_size': '100M',
    'ffmpeg_path': r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    'cookie_file_path': '~/.yt-dlp/cookies.txt',
    'timeout': 300,  # 5分钟超时
    'max_retries': 3
}

# 支持的文件格式
SUPPORTED_FORMATS = {
    'video': ['.mp4', '.flv', '.webm', '.mkv', '.avi', '.mov'],
    'audio': ['.mp3', '.wav', '.flac', '.aac', '.m4a']
}

# 错误消息模板
ERROR_MESSAGES = {
    'no_url_found': '未检测到支持的媒体链接',
    'download_failed': '{platform}下载失败',
    'no_file_found': '下载完成但未找到媒体文件',
    'ffmpeg_missing': 'FFmpeg处理失败，请检查FFmpeg是否正确安装',
    'login_required': '该内容需要登录才能下载',
    'content_protected': '内容受保护，无法下载',
    'timeout': '下载超时，请稍后重试',
    'generic_error': '下载过程中发生错误: {error}'
}