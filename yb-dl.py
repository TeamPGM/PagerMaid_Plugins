""" Pagermaid plugin base. """

from os import remove
from os.path import exists
from youtube_dl import YoutubeDL
from youtube_dl.utils import DownloadError
from re import compile as regex_compile
from pagermaid import bot, log
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(outgoing=True, command=alias_command("ybdl"),
          description="上传 Youtube、Bilibili 视频到 telegram",
          parameters="<url>.")
async def ybdl(context):
    url = context.arguments
    reply = await context.get_reply_message()
    reply_id = None
    await context.edit("获取视频中 . . .")
    if reply:
        reply_id = reply.id
    if url is None:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return

    bilibili_pattern = regex_compile(r"^(http(s)?://)?((w){3}.)?bilibili(\.com)?/.+")
    youtube_pattern = regex_compile(r"^(http(s)?://)?((w){3}.)?youtu(be|.be)?(\.com)?/.+")
    if youtube_pattern.match(url):
        try:
            if not await fetch_video(url, context.chat_id, reply_id):
                await context.edit("出错了呜呜呜 ~ 视频下载失败。")
            await log(f"已拉取UTB视频，地址： {url}.")
            await context.edit("视频获取成功！")
        except DownloadError:
            await context.edit("视频下载失败，可能是视频受到 DRM 保护 或者是 ffmpeg 未安装。")
    if bilibili_pattern.match(url):
        try:
            if not await fetch_video(url, context.chat_id, reply_id):
                await context.edit("出错了呜呜呜 ~ 视频下载失败。")
            await log(f"已拉取 Bilibili 视频，地址： {url}.")
            await context.edit("视频获取成功！")
        except DownloadError:
            await context.edit("视频下载失败，可能是 ffmpeg 未安装。")


async def fetch_video(url, chat_id, reply_id):
    """ Extracts and uploads YouTube video. """
    youtube_dl_options = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': "video.%(ext)s",
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }]
    }
    YoutubeDL(youtube_dl_options).download([url])
    if not exists("video.mp4"):
        return False
    await bot.send_file(
         chat_id,
         "video.mp4",
         reply_to=reply_id
    )
    remove("video.mp4")
    return True
