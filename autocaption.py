from pagermaid import version
from pagermaid.listener import listener
from telethon.tl.custom.message import Message
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeImageSize, \
    DocumentAttributeAudio, DocumentAttributeSticker, DocumentAttributeVideo, DocumentAttributeAnimated


def unit_convert(byte):
    """ Converts byte into readable formats. """
    power = 1024
    zero = 0
    units = {
        0: 'B',
        1: 'KB',
        2: 'MB',
        3: 'GB'}
    while byte > power:
        byte /= power
        zero += 1
    return f"{round(byte, 2)} {units[zero]}"


def duration_convert(duration: int):
    """ Converts duration into readable formats. """
    minutes = duration // 60
    seconds = duration % 60
    hours = minutes // 60
    minutes %= 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@listener(is_plugin=True, outgoing=True, incoming=False, ignore_edited=True)
async def auto_caption_file(context: Message):
    if not context.media:
        return
    if not isinstance(context.media, MessageMediaDocument):
        return
    if context.text:
        text = f"{context.text}\n`=============`\n"
    else:
        text = ""
    for i in context.media.document.attributes:
        # 文件名
        if isinstance(i, DocumentAttributeFilename):
            text += f"`文件名：{i.file_name}`\n"
        # 图片尺寸
        if isinstance(i, DocumentAttributeImageSize):
            text += f"`图片尺寸：{i.w}x{i.h}`\n"
        # 音乐时长、歌手、歌曲名
        if isinstance(i, DocumentAttributeAudio):
            if i.title:
                text += f"`歌曲名：{i.title}`\n"
            if i.performer:
                text += f"`歌手：{i.performer}`\n"
            if not i.voice:
                text += f"`音乐时长：{duration_convert(i.duration)}`\n"
            else:
                text += f"`语音时长：{duration_convert(i.duration)}`\n"
        # 视频时长、尺寸
        if isinstance(i, DocumentAttributeVideo):
            text += f"`视频尺寸：{i.w}x{i.h}`\n"
            text += f"`视频时长：{duration_convert(i.duration)}`\n"
            text += f"`应用内播放：{'是' if i.supports_streaming else '否'}`\n"
            # 过滤○视频
            if i.round_message:
                return
        # 过滤 sticker
        if isinstance(i, DocumentAttributeSticker):
            return
        if isinstance(i, DocumentAttributeAnimated):
            return
    # 文件类型
    text += f"`文件类型：{context.media.document.mime_type}`\n"
    # 文件大小
    text += f"`文件大小：{unit_convert(context.media.document.size)}`\n"
    # DC
    text += f"`DC：{context.media.document.dc_id}`\n"
    # 编辑
    await context.edit(text)
