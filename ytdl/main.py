import contextlib
import os
import pathlib
import shutil
import time
import traceback
import asyncio
import httpx
import importlib

from telethon import types
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo

from pagermaid.enums import Message, AsyncClient
from pagermaid.listener import listener
from pagermaid.services import bot, sqlite as db
from pagermaid.utils import pip_install

dependencies = {
    "yt_dlp": "yt-dlp[curl-cffi]",
    "FastTelethonhelper": "FastTelethonhelper",
}

for module, package in dependencies.items():
    try:
        importlib.import_module(module)
    except ModuleNotFoundError:
        pip_install(package)

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

try:
    from FastTelethonhelper import fast_upload
except ImportError:
    fast_upload = None

ytdl_is_downloading = False

# Common yt-dlp options
base_opts = {
    "default_search": "ytsearch",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "addmetadata": True,
    "noplaylist": True,
}


def ydv_opts(url: str) -> dict:
    """Get video download options based on URL."""
    opts = {
        **base_opts,
        "merge_output_format": "mp4",
        "outtmpl": "data/ytdl/videos/%(title)s.%(ext)s",
        "postprocessor_args": ["-movflags", "+faststart"],
    }
    if "youtube.com" in url or "youtu.be" in url:
        codec = db.get("custom.ytdl_codec", "avc1")
        opts["format"] = (
            f"bestvideo[vcodec^={codec}]+bestaudio/"
            "bestvideo[vcodec!=av01]+bestaudio/"
            "best[vcodec!=av01]"
        )
    else:
        opts["format"] = "bestvideo+bestaudio/best"
    return opts


ydm_opts = {
    **base_opts,
    "format": "bestaudio[vcodec=none]/best",
    "outtmpl": "data/ytdl/audios/%(title)s.%(ext)s",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "best",
        }
    ],
}


def _ytdl_download(url: str, message: Message, loop, opts: dict, file_type_zh: str):
    """Download media using yt-dlp."""
    thumb_path = None
    last_edit_time = time.time()

    def progress_hook(d):
        nonlocal last_edit_time
        if d["status"] == "downloading":
            if time.time() - last_edit_time > 10:
                last_edit_time = time.time()
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total_bytes:
                    downloaded_bytes = d.get("downloaded_bytes")
                    percentage = downloaded_bytes / total_bytes * 100
                    text = f"📥 正在下载{file_type_zh}... {percentage:.1f}%"
                    asyncio.run_coroutine_threadsafe(message.edit(text), loop)

    opts_local = opts.copy()
    opts_local["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(opts_local) as ydl:
            info = ydl.extract_info(url, download=True)
            entry_info = info
            if "entries" in info and info["entries"]:
                entry_info = info["entries"][0]

            file_path = entry_info.get("filepath")
            if not file_path or not os.path.exists(file_path):
                # Fallback to scanning the directory
                outtmpl = opts_local["outtmpl"]
                if isinstance(outtmpl, dict):
                    outtmpl = outtmpl.get("default")
                download_dir = pathlib.Path(outtmpl).parent
                downloaded_files = list(download_dir.glob("*.*"))
                if not downloaded_files:
                    raise DownloadError(
                        "Could not determine the path of the downloaded file."
                    )
                # Get the most recently modified file
                file_path = str(max(downloaded_files, key=os.path.getmtime))

            if os.stat(file_path).st_size > 2 * 1024 * 1024 * 1024 * 0.99:
                raise DownloadError("文件太大(超过 2GB),无法发送。")

            title = entry_info.get("title", "N/A")
            duration = entry_info.get("duration")
            width = entry_info.get("width")
            height = entry_info.get("height")
            thumb_url = entry_info.get("thumbnail")
            webpage_url = entry_info.get("webpage_url")

            if thumb_url:
                thumb_path = "data/ytdl/thumb.jpg"
                with contextlib.suppress(Exception):
                    resp = httpx.get(thumb_url)
                    resp.raise_for_status()
                    with open(thumb_path, "wb") as f:
                        f.write(resp.content)
            return file_path, title, thumb_path, duration, width, height, webpage_url
    except (DownloadError, ExtractorError) as e:
        raise e


async def ytdl_common(message: Message, file_type: str, proxy: str = None):
    if not shutil.which("ffmpeg"):
        return await message.edit(
            "本插件需要 `ffmpeg` 才能正常工作，请先安装 `ffmpeg`。", parse_mode="md",
        )
    global ytdl_is_downloading
    if ytdl_is_downloading:
        return await message.edit("有一个下载任务正在运行中，请不要重复使用命令。")
    ytdl_is_downloading = True

    # Create temporary directory for download
    download_path = pathlib.Path("data/ytdl")
    with contextlib.suppress(Exception):
        shutil.rmtree(download_path)
    download_path.mkdir(parents=True, exist_ok=True)

    url = message.arguments
    if file_type == "audio":
        opts = ydm_opts.copy()
        file_type_zh = "音频"
    else:
        opts = ydv_opts(url)
        file_type_zh = "视频"
    if proxy:
        opts["proxy"] = proxy
    message: Message = await message.edit(f"📥 正在请求{file_type_zh}...")

    try:
        (
            file_path,
            title,
            thumb_path,
            duration,
            width,
            height,
            webpage_url,
        ) = await bot.loop.run_in_executor(
            None, _ytdl_download, url, message, bot.loop, opts, file_type_zh
        )

        caption = f"<code>{title}</code>"
        if webpage_url:
            caption += f"\n<a href='{webpage_url}'>Original URL</a>"

        attributes = []
        if duration:
            if file_type == "video":
                attributes.append(
                    DocumentAttributeVideo(
                        duration=duration, w=width or 0, h=height or 0
                    )
                )
            else:
                attributes.append(
                    DocumentAttributeAudio(duration=duration, title=title)
                )

        if fast_upload:
            file = await fast_upload(
                bot, file_path, message, os.path.basename(file_path)
            )
            await bot.send_file(
                message.chat_id,
                file,
                thumb=thumb_path,
                caption=caption,
                force_document=False,
                attributes=attributes,
                workers=4,
                parse_mode="html",
                supports_streaming=True,
            )
            await message.delete()
        else:
            await message.edit(f"📤 正在上传{file_type_zh}...")
            last_edit_time = time.time()

            async def progress(current, total):
                nonlocal last_edit_time
                if time.time() - last_edit_time > 10:
                    last_edit_time = time.time()
                    with contextlib.suppress(Exception):
                        await message.edit(
                            f"📤 正在上传{file_type_zh}... {current / total:.2%}"
                        )

            await bot.send_file(
                message.chat_id,
                file_path,
                thumb=thumb_path,
                caption=caption,
                force_document=False,
                attributes=attributes,
                progress_callback=progress,
                workers=4,
                parse_mode="html",
                supports_streaming=True,
            )
            await message.delete()
    except DownloadError as e:
        if "Unsupported URL" in str(e):
            await message.edit("下载失败：不支持的 URL 或该网站暂时无法下载。")
        else:
            await message.edit(
                f"下载/发送文件失败，发生错误：\n<code>{traceback.format_exc()}</code>",
                parse_mode="html",
            )
    except Exception as e:
        await message.edit(
            f"下载/发送文件失败，发生错误：\n<code>{traceback.format_exc()}</code>",
            parse_mode="html",
        )
    finally:
        ytdl_is_downloading = False
        with contextlib.suppress(Exception):
            shutil.rmtree(download_path)


ytdl_help = (
    "**Youtube-dl**\n\n"
    "使用方法: `ytdl [m] <链接/关键词> | _proxy [<url>] | _codec [<codec>] | update`\n\n"
    " - `ytdl <链接/关键词>`: 下载视频 (默认)\n"
    " - `ytdl m <链接/关键词>`: 下载音频\n"
    " - `ytdl _proxy <url>`: 设置 HTTP/SOCKS 代理\n"
    " - `ytdl _proxy`: 删除代理\n"
    " - `ytdl _codec <codec>`: 设置优先选择的 Youtube 视频编码 (默认 avc1, 可选 vp9/av01)\n"
    " - `ytdl _codec`: 删除优先选择的 Youtube 视频编码\n"
    " - `ytdl update`: 更新 yt-dlp"
)


@listener(
    command="ytdl",
    description="从各种网站下载视频或音频。\n\n" + ytdl_help,
    parameters="[m] <链接/关键词> | _proxy [<url>] | _codec [<codec>] | update",
)
async def ytdl(message: Message, client: AsyncClient):
    """
    Downloads videos or audio from various sites.
    - `ytdl <url/keyword>`: download video
    - `ytdl m <url/keyword>`: download audio
    - `ytdl _proxy <url>`: set HTTP/SOCKS proxy
    - `ytdl _proxy`: delete proxy
    - `ytdl _codec <codec>`: set preferred video codec
    - `ytdl _codec`: reset preferred video codec
    - `ytdl update`: update yt-dlp
    """
    arguments = message.arguments
    if arguments.startswith("_proxy"):
        parts = arguments.split(" ", 1)
        if len(parts) > 1 and parts[1]:
            db["custom.ytdl_proxy"] = parts[1]
            return await message.edit(f"代理已设置为: `{parts[1]}`")
        else:
            proxy = db.get("custom.ytdl_proxy")
            if proxy:
                del db["custom.ytdl_proxy"]
                return await message.edit(f"代理 `{proxy}` 已删除。")
            else:
                return await message.edit("未设置代理。")

    if arguments.startswith("_codec"):
        parts = arguments.split(" ", 1)
        if len(parts) > 1 and parts[1]:
            db["custom.ytdl_codec"] = parts[1]
            return await message.edit(f"Youtube 优先视频编码已设置为: `{parts[1]}`")
        else:
            codec = db.get("custom.ytdl_codec")
            if codec:
                del db["custom.ytdl_codec"]
                return await message.edit(f"Youtube 优先视频编码 `{codec}` 已删除。")
            else:
                return await message.edit("Youtube 未设置优先视频编码。")

    if arguments == "update":
        await ytdl_update(message, client)
        return
    if not arguments:
        return await message.edit(ytdl_help, parse_mode="markdown")

    parts = arguments.split(" ", 1)
    is_audio = parts[0] == "m"

    if is_audio:
        if len(parts) < 2 or not parts[1].strip():
            return await message.edit(ytdl_help, parse_mode="markdown")
        message.arguments = parts[1]
        file_type = "audio"
    else:
        message.arguments = arguments
        file_type = "video"

    proxy = db.get("custom.ytdl_proxy")
    await ytdl_common(message, file_type, proxy)


async def ytdl_update(message: Message, client: AsyncClient):
    """强制更新 yt-dlp 到最新版本。"""
    await message.edit("正在更新 yt-dlp...")
    try:
        req = await client.get("https://pypi.org/pypi/yt-dlp/json")
        data = req.json()
        latest_version = data["info"]["version"]
    except Exception:
        await message.edit("获取最新版本信息失败，请稍后再试。")
        return
    pip_install("yt-dlp[curl-cffi]", version=f">={latest_version}", alias="a")
    await message.edit(f"yt-dlp 已更新到最新版本：{latest_version}。重启 PagerMaid 后生效。")
