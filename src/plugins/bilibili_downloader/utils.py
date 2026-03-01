import os
from pathlib import Path
from typing import Optional


def get_cookie_path() -> str:
    """
    获取cookie文件的路径
    """
    return os.path.expanduser('~/.yt-dlp/cookies.txt')


def check_cookies_exists() -> bool:
    """
    检查cookie文件是否存在
    """
    cookie_path = get_cookie_path()
    return os.path.exists(cookie_path)


def validate_cookies_for_platform(platform: str) -> bool:
    """
    验证特定平台的cookies是否存在
    """
    if platform in ['douyin', 'xiaohongshu', 'weibo']:
        # 这些平台通常需要cookies
        return check_cookies_exists()
    return True  # 其他平台不一定需要


def get_formatted_cookie_path() -> str:
    """
    获取格式化的cookie路径显示
    """
    return get_cookie_path()


def setup_cookies_guide(platform: str) -> str:
    """
    为特定平台生成设置cookies的指南
    """
    guide = f"""
检测到您正在尝试下载{platform}平台的内容。
{platform}可能需要有效的登录cookies才能下载。

设置步骤：
1. 在浏览器中登录{platform}账号
2. 安装浏览器扩展如 "Get cookies.txt" 
3. 导出cookies为 Netscape 格式并保存为 cookies.txt
4. 将 cookies.txt 放置到以下路径：
   {get_formatted_cookie_path()}

注意：某些平台需要定期更新cookies以保持有效性。
    """
    return guide