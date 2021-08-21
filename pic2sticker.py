""" PagerMaid module to handle sticker collection. """

from io import BytesIO
from telethon.tl.types import DocumentAttributeFilename, MessageMediaPhoto, MessageMediaWebPage
from PIL import Image, ImageOps
from math import floor
from pagermaid import bot, redis, redis_status
from pagermaid.listener import listener
from pagermaid.utils import lang, alias_command


@listener(is_plugin=False, outgoing=True, command=alias_command("pic2sticker"),
          description='将图片转换为贴纸',
          parameters="<round>")
async def pic2sticker(context):
    """ Fetches images and send it as sticker. """
    pic_round = False
    if len(context.parameter) >= 1:
        pic_round = True

    if redis_status():
        if redis.get("sticker.round"):
            pic_round = True

    message = await context.get_reply_message()
    if message and message.media:
        if isinstance(message.media, MessageMediaPhoto):
            photo = BytesIO()
            photo = await bot.download_media(message.photo, photo)
        elif isinstance(message.media, MessageMediaWebPage):
            try:
                await context.edit(lang('sticker_type_not_support'))
            except:
                pass
            return
        elif "image" in message.media.document.mime_type.split('/'):
            photo = BytesIO()
            try:
                await context.edit(lang('sticker_downloading'))
            except:
                pass
            await bot.download_file(message.media.document, photo)
            if (DocumentAttributeFilename(file_name='sticker.webp') in
                    message.media.document.attributes):
                try:
                    await context.edit(lang('sticker_type_not_support'))
                except:
                    pass
                return
        else:
            try:
                await context.edit(lang('sticker_type_not_support'))
            except:
                pass
            return
    else:
        try:
            await context.edit(lang('sticker_reply_not_sticker'))
        except:
            pass
        return

    if photo:
        file = BytesIO()
        try:
            await context.edit(lang('sticker_resizing'))
        except:
            pass
        image = await resize_image(photo)
        if pic_round:
            try:
                await context.edit(lang('us_static_rounding'))
            except:
                pass
            image = await rounded_image(image)
        file.name = "sticker.webp"
        image.save(file, "WEBP")
        file.seek(0)
        try:
            await context.edit(lang('us_static_uploading'))
        except:
            pass
        await bot.send_file(context.chat_id, file, force_document=False)
        try:
            await context.delete()
        except:
            pass


async def resize_image(photo):
    image = Image.open(photo)
    maxsize = (512, 512)
    if (image.width and image.height) < 512:
        size1 = image.width
        size2 = image.height
        if image.width > image.height:
            scale = 512 / size1
            size1new = 512
            size2new = size2 * scale
        else:
            scale = 512 / size2
            size1new = size1 * scale
            size2new = 512
        size1new = floor(size1new)
        size2new = floor(size2new)
        size_new = (size1new, size2new)
        image = image.resize(size_new)
    else:
        image.thumbnail(maxsize)

    return image


async def rounded_image(image):
    w = image.width
    h = image.height
    # 比较长宽
    if w > h:
        resize_size = h
    else:
        resize_size = w
    half_size = floor(resize_size / 2)

    # 获取圆角模版，切割成4个角
    tl = (0, 0, 256, 256)
    tr = (256, 0, 512, 256)
    bl = (0, 256, 256, 512)
    br = (256, 256, 512, 512)
    border = Image.open('pagermaid/static/images/rounded.png').convert('L')
    tlp = border.crop(tl)
    trp = border.crop(tr)
    blp = border.crop(bl)
    brp = border.crop(br)

    # 缩放四个圆角
    tlp = tlp.resize((half_size, half_size))
    trp = trp.resize((half_size, half_size))
    blp = blp.resize((half_size, half_size))
    brp = brp.resize((half_size, half_size))

    # 扩展四个角大小到目标图大小
    # tlp = ImageOps.expand(tlp, (0, 0, w - tlp.width, h - tlp.height))
    # trp = ImageOps.expand(trp, (w - trp.width, 0, 0, h - trp.height))
    # blp = ImageOps.expand(blp, (0, h - blp.height, w - blp.width, 0))
    # brp = ImageOps.expand(brp, (w - brp.width, h - brp.height, 0, 0))

    # 四个角合并到一张新图上
    ni = Image.new('RGB', (w, h), (0, 0, 0)).convert('L')
    ni.paste(tlp, (0, 0))
    ni.paste(trp, (w - trp.width, 0))
    ni.paste(blp, (0, h - blp.height))
    ni.paste(brp, (w - brp.width, h - brp.height))

    # 合并圆角和原图
    image.putalpha(ImageOps.invert(ni))

    return image
