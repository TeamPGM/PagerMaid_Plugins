import contextlib
import os
import pathlib
import shutil
import traceback
import asyncio
import importlib.metadata
import json
import mimetypes

from telethon import types
from PIL import Image

from pagermaid.enums import Message, AsyncClient
from pagermaid.listener import listener
from pagermaid.services import bot, sqlite as db
from pagermaid.utils import pip_install

# Dependency check
dependencies = {
    "gallery-dl",
    "FastTelethonhelper",
}
for package in dependencies:
    try:
        importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        pip_install(package)

try:
    from FastTelethonhelper import fast_upload
except ImportError:
    fast_upload = None

gallery_dl_is_downloading = False


async def get_video_metadata(file_path: pathlib.Path) -> (int, int, int, pathlib.Path):
    """
    Get video metadata using ffprobe and generate a thumbnail using ffmpeg.
    Returns: (width, height, duration, thumb_path)
    """
    try:
        # Get video metadata
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return 0, 0, 0, None

        metadata = stdout.decode().strip().split('\n')
        if len(metadata) < 3:
            return 0, 0, 0, None
        width, height, duration = int(metadata[0]), int(metadata[1]), int(float(metadata[2]))

        # Generate thumbnail
        thumb_path = file_path.with_suffix(".jpg")
        thumb_cmd = [
            "ffmpeg", "-i", str(file_path),
            "-ss", "00:00:01.000", "-vframes", "1",
            str(thumb_path), "-y"
        ]
        process = await asyncio.create_subprocess_exec(
            *thumb_cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if process.returncode != 0:
            with contextlib.suppress(FileNotFoundError):
                os.remove(thumb_path)
            return width, height, duration, None

        return width, height, duration, thumb_path
    except (ValueError, IndexError, Exception):
        return 0, 0, 0, None


def _parse_author(author_val):
    """Parses the author value which can be a string, a JSON string, a dict, or a list."""
    if not author_val:
        return None
    parsed_data = author_val
    if isinstance(author_val, str):
        with contextlib.suppress(json.JSONDecodeError):
            parsed_data = json.loads(author_val)
    if isinstance(parsed_data, dict):
        return parsed_data.get("name", parsed_data.get("displayName", str(parsed_data)))
    if isinstance(parsed_data, list):
        return ", ".join(map(str, parsed_data))
    return str(author_val)


def _extract_metadata(download_path: pathlib.Path, default_url: str) -> dict:
    """Extracts metadata from gallery-dl JSON files."""
    metadata = {
        "title": "N/A", "author_key": None, "author_val": None,
        "site": None, "tags": None, "final_url": default_url,
    }
    metadata_json_files = list(download_path.rglob("*.json"))
    if not metadata_json_files:
        return metadata
    try:
        with open(metadata_json_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        metadata.update({
            "title": data.get("title", "N/A"),
            "final_url": data.get("webpage_url", default_url),
            "site": data.get("category"),
            "tags": data.get("tags"),
        })
        if data.get("artist"):
            metadata.update({"author_key": "Artist", "author_val": _parse_author(data.get("artist"))})
        elif data.get("author"):
            metadata.update({"author_key": "Author", "author_val": _parse_author(data.get("author"))})
        elif data.get("uploader"):
            metadata.update({"author_key": "Uploader", "author_val": _parse_author(data.get("uploader"))})
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        pass
    return metadata


def _build_caption(metadata: dict) -> str:
    """Builds a caption from extracted metadata."""
    parts = []
    if metadata.get("keyword"):
        parts.append(f"<b>Keyword:</b> {metadata['keyword']}")
    elif metadata.get("title") and metadata["title"] != "N/A":
        parts.append(f"<b>Title:</b> {metadata['title']}")
    if metadata["author_key"] and metadata["author_val"] and metadata["author_val"] != "N/A":
        parts.append(f"<b>{metadata['author_key']}:</b> {metadata['author_val']}")
    if metadata["site"]:
        parts.append(f"<b>Site:</b> {metadata['site']}")
    if metadata["tags"] and isinstance(metadata["tags"], list):
        parts.append(f"<b>Tags:</b> {', '.join(metadata['tags'])}")
    parts.append(f'<a href="{metadata["final_url"]}">Original URL</a>')
    return "\n".join(parts)


def _check_and_convert_image(file_path: pathlib.Path) -> pathlib.Path:
    """
    Checks, resizes, and converts images to be compliant with Telegram's requirements.
    - Resizes images where the longest side exceeds 3000 pixels.
    - Converts WEBP and AVIF files to JPG.
    """
    mime_type = mimetypes.guess_type(file_path.name)[0] or ""
    if not mime_type.startswith("image/"):
        return file_path

    try:
        with Image.open(file_path) as img:
            width, height = img.size
            is_unsupported_format = file_path.suffix.lower() in [".webp", ".avif"]
            needs_resize = max(width, height) > 3000

            if not is_unsupported_format and not needs_resize:
                return file_path

            # Perform resizing if needed
            if needs_resize:
                ratio = 3000 / max(width, height)
                img = img.resize((int(width * ratio), int(height * ratio)), Image.Resampling.LANCZOS)

            # Determine the new path and format
            new_path = file_path
            save_format = (img.format or 'JPEG').upper()
            if is_unsupported_format:
                new_path = file_path.with_suffix(".jpg")
                save_format = "JPEG"

            # Convert to RGB to drop alpha channel for JPEG
            if save_format == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")

            # Save the image
            img.save(new_path, save_format)

            # Remove original file if a new one was created
            if file_path != new_path:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(file_path)
            return new_path
    except Exception:
        # If conversion fails, return original path and hope for the best
        return file_path


async def _run_gallery_dl(url: str, download_path: pathlib.Path, proxy: str = None, extra_args: list = None):
    """Constructs and runs the gallery-dl command."""
    cmd = ["gallery-dl", "--write-metadata", "--download-archive", str(download_path / "archive.txt"), "-d",
           str(download_path)]
    if proxy:
        cmd.extend(["--proxy", proxy])
    config_path = pathlib.Path("data/gdl/config.json")
    if config_path.is_file():
        cmd.extend(["-c", str(config_path)])
    if extra_args:
        cmd.extend(extra_args)
    exec_cmd = 'f="{}"; case "$f" in *.flv|*.avi|*.mov|*.wmv|*.m4v) ffmpeg -i "$f" -c copy "${{f%.*}}.mp4" -y && rm "$f" ;; esac'
    cmd.extend(["--exec", exec_cmd, url])
    return await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)


async def _upload_files(message: Message, files: list[pathlib.Path], caption: str):
    """Separates files into media and others, then uploads them."""
    reply_to = message.reply_to_msg_id or None
    media_files, other_files, thumbs_to_clean = [], [], []
    for p in files:
        mime_type = mimetypes.guess_type(p.name)[0] or ""
        if mime_type.startswith("image/") or mime_type.startswith("video/"):
            media_files.append(p)
        else:
            other_files.append(p)

    async def upload_file(file_path):
        return (await fast_upload(bot, str(file_path)), None) if fast_upload else (file_path, None)

    if media_files:
        album_files = []
        for file_path in media_files:
            if not fast_upload:
                album_files.append(file_path)
                continue
            uploaded_file, _ = await upload_file(file_path)
            thumb, attributes = None, []
            if (mimetypes.guess_type(file_path.name)[0] or "").startswith("video/"):
                width, height, duration, thumb_path = await get_video_metadata(file_path)
                if thumb_path:
                    thumbs_to_clean.append(thumb_path)
                    thumb, _ = await upload_file(thumb_path)
                attributes.append(
                    types.DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True))
            if (mimetypes.guess_type(file_path.name)[0] or "").startswith("image/"):
                album_files.append(types.InputMediaUploadedPhoto(file=uploaded_file))
            else:
                album_files.append(types.InputMediaUploadedDocument(
                    file=uploaded_file, thumb=thumb,
                    mime_type=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
                    attributes=attributes
                ))
        for i in range(0, len(album_files), 10):
            chunk = album_files[i:i + 10]
            await bot.send_file(
                message.chat_id, chunk, reply_to=reply_to, parse_mode="html",
                caption=caption if len(album_files) <= 10 else f"<b>#{i // 10 + 1}</b>\n{caption}"
            )
            await asyncio.sleep(1)

    if other_files:
        for i, file_path in enumerate(other_files):
            uploaded_file, _ = await upload_file(file_path)
            await bot.send_file(
                message.chat_id, uploaded_file, force_document=True, reply_to=reply_to,
                caption=caption if not media_files and i == 0 else "", parse_mode="html"
            )
            await asyncio.sleep(1)

    for thumb in thumbs_to_clean:
        with contextlib.suppress(FileNotFoundError):
            os.remove(thumb)


async def gallery_dl_common(message: Message, proxy: str = None, extra_args: list = None, keyword: str = None):
    global gallery_dl_is_downloading
    if gallery_dl_is_downloading:
        return await message.edit("有一个下载任务正在运行中，请不要重复使用命令。" )
    gallery_dl_is_downloading = True
    gid = f"{message.chat_id}.{message.id}"
    download_path = pathlib.Path(f"data/gdl/{gid}")
    download_path.mkdir(parents=True, exist_ok=True)
    try:
        url = message.arguments
        message: Message = await message.edit("正在下载文件...")
        process = await _run_gallery_dl(url, download_path, proxy, extra_args)
        _, stderr = await process.communicate()
        if process.returncode != 0:
            return await message.edit(f"下载失败：\n<code>{stderr.decode().strip()}</code>", parse_mode="html")

        files = sorted([p for p in download_path.rglob("*") if
                        p.is_file() and p.suffix != ".json" and p.name != "archive.txt" and p.stat().st_size > 0])
        if not files:
            return await message.edit("没有下载到任何文件。" )

        await message.edit(f"下载完成，正在上传 {len(files)} 个文件...")
        processed_files = [_check_and_convert_image(p) for p in files]
        metadata = _extract_metadata(download_path, url)
        if keyword:
            metadata["keyword"] = keyword
        caption = _build_caption(metadata)
        await _upload_files(message, processed_files, caption)
        await message.delete()
    except Exception:
        await message.edit(f"下载/发送文件失败，发生错误：\n<code>{traceback.format_exc()}</code>", parse_mode="html")
    finally:
        gallery_dl_is_downloading = False
        shutil.rmtree(download_path, ignore_errors=True)


@listener(
    command="gdl",
    description="从各种网站下载图片/视频。",
    parameters="<链接> | _proxy [<proxy_url>] | update | _pixiv <关键字>",
)
async def gallery_dl_main(message: Message, client: AsyncClient):
    """
    Downloads image/video galleries from various sites.
    - `gdl <url>`: download gallery
    - `gdl _proxy <proxy_url>`: set HTTP/SOCKS proxy
    - `gdl _proxy`: delete proxy
    - `gdl update`: update gallery-dl
    - `gdl _pixiv <keyword>`: download popular illustrations from pixiv by keyword
    """
    arguments = message.arguments
    if arguments.startswith("_proxy"):
        parts = arguments.split(" ", 1)
        if len(parts) > 1 and parts[1]:
            db["custom.gdl_proxy"] = parts[1]
            return await message.edit(f"代理已设置为: `{parts[1]}`")
        else:
            proxy = db.get("custom.gdl_proxy")
            if proxy:
                del db["custom.gdl_proxy"]
                return await message.edit(f"代理 `{proxy}` 已删除。" )
            else:
                return await message.edit("未设置代理。" )

    if arguments == "update":
        await gallery_dl_update(message, client)
        return

    if arguments.startswith("_pixiv"):
        parts = arguments.split(" ", 1)
        if len(parts) > 1 and parts[1]:
            keyword = parts[1]
            url = f'https://www.pixiv.net/tags/{keyword}/popular'
            message.arguments = url
            proxy = db.get("custom.gdl_proxy")
            await gallery_dl_common(message, proxy, extra_args=["--range", "1-10"], keyword=keyword)
        else:
            await message.edit("请提供 Pixiv 搜索关键字。" )
        return

    if not arguments:
        return await message.edit(
            "**gdl**\n\n"
            "使用方法: `gdl <链接> | _proxy [<url>] | update | _pixiv <关键字>`\n\n"
            " - `gdl <链接>`: 下载图片/视频\n"
            " - `gdl _pixiv <关键字>`: 下载 pixiv 热门插画\n"
            " - `gdl _proxy <url>`: 设置 HTTP/SOCKS 代理\n"
            " - `gdl _proxy`: 删除代理\n"
            " - `gdl update`: 更新 gallery-dl\n",
            "详细使用说明: https://github.com/TeamPGM/PagerMaid_Plugins/blob/master/gdl/DES.md",
            parse_mode="markdown"
        )

    proxy = db.get("custom.gdl_proxy")
    await gallery_dl_common(message, proxy)


async def gallery_dl_update(message: Message, client: AsyncClient):
    """强制更新 gallery-dl 到最新版本。"""
    await message.edit("正在更新 gallery-dl...")
    try:
        req = await client.get("https://pypi.org/pypi/gallery-dl/json")
        data = req.json()
        latest_version = data["info"]["version"]
    except Exception:
        return await message.edit("获取最新版本信息失败，请稍后再试。" )
    pip_install("gallery-dl", version=f">={latest_version}", alias="gallery-dl")
    await message.edit(f"gallery-dl 已更新到最新版本：{latest_version}。" )
