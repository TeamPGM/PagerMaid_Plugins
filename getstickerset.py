from telethon.errors import StickersetInvalidError, FileMigrateError
from telethon.tl.custom.message import Message
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import DocumentAttributeFilename, InputStickerSetEmpty, InputStickerSetID, StickerSet, \
    InputStickerSetThumb, MessageMediaPhoto
from PIL import Image
from pytz import timezone
from pagermaid import bot
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("getstickerset"),
          description="获取所回复贴纸的贴纸包信息。")
async def get_sticker_set(context: Message):
    """ get sticker set """
    reply = await context.get_reply_message()
    if not reply:
        await context.edit('出错了呜呜呜 ~ 没有回复贴纸消息。')
        return
    if not reply.media:
        await context.edit('出错了呜呜呜 ~ 没有回复贴纸消息。')
        return
    if isinstance(reply.media, MessageMediaPhoto):
        await context.edit('出错了呜呜呜 ~ 没有回复贴纸消息。')
        return
    elif "image" in reply.media.document.mime_type.split('/'):
        if (DocumentAttributeFilename(file_name='sticker.webp') not in
                reply.media.document.attributes):
            await context.edit('出错了呜呜呜 ~ 没有回复贴纸消息。')
            return
    elif (DocumentAttributeFilename(file_name='AnimatedSticker.tgs') in
          reply.media.document.attributes):
        pass
    else:
        await context.edit('出错了呜呜呜 ~ 没有回复贴纸消息。')
        return
    sticker_set = reply.media.document.attributes[1].stickerset
    if isinstance(sticker_set, InputStickerSetEmpty):
        await context.edit('出错了呜呜呜 ~ 您回复的贴纸不包含任何贴纸包信息。')
        return
    await context.edit('获取中。。。')
    try:
        stickers = await context.client(GetStickerSetRequest(
            stickerset=InputStickerSetID(id=sticker_set.id, access_hash=sticker_set.access_hash)))
    except StickersetInvalidError:
        await context.edit('出错了呜呜呜 ~ 您回复的贴纸不包含任何贴纸包信息。')
        return
    stickers_set = stickers.set
    # 再次判断变量类型
    if not isinstance(stickers_set, StickerSet):
        await context.edit('出错了呜呜呜 ~ 您回复的贴纸不包含任何贴纸包信息。')
        return
    # 初始化变量
    sid = sticker_set.id
    access_hash = sticker_set.access_hash
    thumb_version = stickers_set.thumb_version
    official = '✅' if stickers_set.official else ''
    animated = '（动态）' if stickers_set.animated else ''
    archived = '💤' if stickers_set.archived else ''
    time_zone = timezone('Etc/GMT-8')
    installed_date = stickers_set.installed_date.astimezone(time_zone).strftime('%Y-%m-%d %H:%M:%S') if \
        stickers_set.installed_date else '未添加'
    # 下载预览图
    file = None
    if thumb_version:
        try:
            thumb = await bot(GetFileRequest(location=InputStickerSetThumb(
                stickerset=InputStickerSetID(id=sid, access_hash=access_hash),
                thumb_version=thumb_version), offset=-1, limit=1048576, precise=False, cdn_supported=True))
            with open('data/sticker_thumb.jpg', 'wb') as f:
                f.write(thumb.bytes)
            file = 'data/sticker_thumb.jpg'
        except FileMigrateError:
            pass
    else:
        if not stickers_set.animated:
            await bot.download_media(stickers.documents[0], file='data/sticker_thumb.webp')
            convert_png('data/sticker_thumb.webp')
            file = 'data/sticker_thumb.png'
    text = f'贴纸包：{official}[{stickers_set.title}](https://t.me/addstickers/{stickers_set.short_name}) {animated}' \
           f'{archived}\n' \
           f'贴纸数：`{stickers_set.count}`\n' \
           f'添加时间：`{installed_date}`\n' \
           f'id：`{sid}`\n' \
           f'access_hash: `{access_hash}`'
    if file:
        await context.client.send_file(
            context.chat_id,
            file,
            caption=text,
            force_document=False,
            allow_cache=False
        )
        await context.delete()
    else:
        await context.edit(text)


def convert_png(path):
    im = Image.open(path)
    im = im.convert('RGBA')
    new_path = path.replace(".webp", ".png")
    im.save(new_path, 'PNG')
    return new_path
