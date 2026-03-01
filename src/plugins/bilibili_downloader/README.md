# 多媒体下载器插件

## 功能介绍

这是一个增强版的多媒体下载器插件，支持从多个平台自动下载视频内容。

## 支持的平台

### 🎬 视频平台
- **哔哩哔哩 (Bilibili)** - 支持BV号、av号、番剧链接
- **YouTube** - 支持常规视频链接
- **抖音 (Douyin)** - 支持抖音视频链接
- **小红书 (Xiaohongshu)** - 支持小红书视频链接
- **微博 (Weibo)** - 支持微博视频链接
- **TikTok** - 支持国际版抖音链接

## 使用方法

### 基本使用
在QQ群聊或私聊中发送任意支持平台的视频链接，机器人会自动识别并下载视频。

### 支持的链接格式示例

**哔哩哔哩:**
- `https://www.bilibili.com/video/BV1xx411c7mu`
- `https://b23.tv/abc123`
- `https://www.bilibili.com/video/av123456`

**YouTube:**
- `https://www.youtube.com/watch?v=xxxxxx`
- `https://youtu.be/xxxxxx`

**抖音:**
- `https://www.douyin.com/video/xxxxxxxxx`
- `https://v.douyin.com/xxxxxx`

**小红书:**
- `https://www.xiaohongshu.com/discovery/item/xxxxxx`
- `https://xhslink.com/xxxxxx`

**微博:**
- `https://weibo.com/tv/show/xxxxxx`
- `https://weibo.cn/xxxxxx`

**TikTok:**
- `https://www.tiktok.com/@username/video/xxxxx`
- `https://vm.tiktok.com/xxxxxx`

## 登录凭证和Cookies配置

对于需要登录的平台（如抖音、小红书等），以及需要会员权限才能下载的视频（如B站大会员视频），您需要配置相应的cookies文件以实现下载。

### 如何获取Cookies文件

#### 方法一：使用浏览器扩展（推荐）

**Chrome浏览器：**

1. 访问Chrome网上应用店，搜索并安装 "Get cookies.txt LOCALLY" 扩展
2. 登录您需要下载视频的平台账号（例如：B站、抖音、小红书等）
3. 在扩展图标上点击右键，选择"选项"，将"SameSite values"设置为"Discard"
4. 访问您想要下载的视频页面
5. 点击浏览器工具栏上的扩展图标，点击"Save cookies.txt"按钮
6. 将下载的 cookies.txt 文件重命名为 cookies.txt

**Firefox浏览器：**

1. 访问Firefox附加组件网站，搜索并安装 "Export Cookies" 扩展
2. 登录您需要下载视频的平台账号
3. 访问您想要下载的视频页面
4. 点击扩展图标，选择"Export"，保存为 Netscape 格式

#### 方法二：手动获取

1. 登录相应平台账号
2. 打开浏览器开发者工具 (F12)
3. 访问一个视频页面
4. 在 Network (网络) 标签页中找到请求
5. 右键点击第一个请求，选择"Copy" → "Copy value"或"Copy as cURL"
6. 从中提取 Cookie 字段的值

### 如何放置Cookies文件

将获取到的 cookies.txt 文件放置到以下位置：

- **Windows:** `%USERPROFILE%\.yt-dlp\cookies.txt`
  - 具体路径通常是：`C:\Users\[用户名]\.yt-dlp\cookies.txt`
  
- **Linux/macOS:** `~/.yt-dlp/cookies.txt`

**在Windows上创建路径的步骤：**
1. 按 Win+R 键打开"运行"对话框
2. 输入 `%USERPROFILE%` 并回车
3. 在打开的文件夹中创建名为 `.yt-dlp` 的文件夹
4. 将 cookies.txt 文件放入此文件夹

**在Linux/macOS上创建路径的步骤：**
```bash
mkdir -p ~/.yt-dlp
cp [cookies文件路径] ~/.yt-dlp/cookies.txt
```

### 特定平台登录提示

- **Bilibili**: 需要登录大会员账号才能下载会员专享视频
- **抖音**: 需要登录账号才能下载大部分视频，建议使用手机APP扫码登录获取有效cookies
- **小红书**: 需要登录账号，部分视频需要登录后才能访问
- **微博**: 某些视频需要登录才能下载
- **YouTube**: 一般情况下不需要登录，但某些受限视频可能需要

### 注意事项

- Cookies有有效期，可能需要定期更新
- 对于某些平台，需要保持登录状态才能获取有效的cookies
- 请妥善保管您的cookies文件，其中包含敏感的登录信息
- 某些平台可能需要特定的headers或token，这时cookies文件特别重要

## 配置说明

### 环境要求
- **FFmpeg**: 必须安装并配置到系统PATH中
- **Cookie文件**: 可选，用于某些需要登录的平台

### 配置文件
主要配置在 `config.py` 文件中：

```python
# 全局设置
GLOBAL_SETTINGS = {
    'ffmpeg_path': r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",  # FFmpeg路径
    'cookie_file_path': '~/.yt-dlp/cookies.txt',  # Cookie文件路径
    'timeout': 300,  # 下载超时时间(秒)
}
```

### 平台特定配置
每个平台都有独立的配置项：
```python
'bilibili': {
    'name': '哔哩哔哩',
    'patterns': [...],      # URL匹配规则
    'format_selector': '...',  # 视频格式选择器
    'user_agent': '...',    # 用户代理
    'referer': '...',       # 来源页面
    'max_resolution': '1080p'  # 最大分辨率
}
```

## 错误处理

插件会根据不同的错误类型返回相应的提示信息：

- **FFmpeg相关错误**: 提示安装或配置FFmpeg
- **登录_required**: 提示需要登录账户
- **内容保护**: 提示内容受版权保护
- **超时错误**: 提示网络连接问题
- **通用错误**: 显示具体的错误信息

## 注意事项

1. **文件大小限制**: 默认限制100MB，可在配置中调整
2. **下载时效**: 临时文件会在下载完成后自动清理
3. **平台限制**: 某些平台可能需要特殊处理或登录
4. **网络环境**: 建议在稳定的网络环境下使用

## 扩展支持

要添加新的平台支持，只需在 `config.py` 中添加相应配置：

```python
'new_platform': {
    'name': '新平台名称',
    'patterns': [r'新平台的URL正则表达式'],
    'format_selector': '视频格式选择器',
    'user_agent': '用户代理字符串',
    'referer': '来源页面',
}
```

## 依赖说明

- `yt-dlp`: 核心下载库
- `nonebot2`: QQ机器人框架
- `ffmpeg`: 视频处理工具

## 版本历史

- v2.0: 重构为多平台支持架构
- v1.0: 初始版本，仅支持B站