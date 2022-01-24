from pagermaid import version
from pagermaid.listener import listener
from telethon.tl.custom.message import Message
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeImageSize


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
    # 文件类型
    text += f"`文件类型：{context.media.document.mime_type}`\n"
    # 文件大小
    text += f"`文件大小：{unit_convert(context.media.document.size)}`\n"
    # DC
    text += f"`DC：{context.media.document.dc_id}`\n"
    # 编辑
    await context.edit(text)
