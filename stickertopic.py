from time import sleep
from os import remove
from urllib import request
from io import BytesIO
from telethon.tl.types import DocumentAttributeFilename, MessageMediaPhoto
from PIL import Image
from math import floor
from pagermaid import bot
from pagermaid.listener import listener
from random import random


@listener(outgoing=True, command="pic",
          description="将你回复的静态贴纸转换为图片")
async def stickertopic(context):
    user = await bot.get_me()
    if not user.username:
        user.username = user.first_name
    message = await context.get_reply_message()
    custom_emoji = False
    animated = False
    await context.edit("开始转换...\n███30%")
    if message and message.media:
        if isinstance(message.media, MessageMediaPhoto):
            photo = BytesIO()
            photo = await bot.download_media(message.photo, photo)
        elif "image" in message.media.document.mime_type.split('/'):
            photo = BytesIO()
            await context.edit("正在转换...\n██████60%")
            await bot.download_file(message.media.document, photo)
            if (DocumentAttributeFilename(file_name='sticker.webp') in
                    message.media.document.attributes):
                custom_emoji = True
        elif (DocumentAttributeFilename(file_name='AnimatedSticker.tgs') in
              message.media.document.attributes):
            photo = BytesIO()
            await bot.download_file(message.media.document, "AnimatedSticker.tgs")
            for _ in range(len(message.media.document.attributes)):
                try:
                    break
                except:
                    pass
            custom_emoji = True
            animated = True
            photo = 1
        else:
            await context.edit("出错了呜呜呜 ~ 目标不是贴纸 。")
            sleep(2)
            await context.delete()
            return
    else:
        await context.edit("出错了呜呜呜 ~ 目标不是贴纸 。")
        sleep(2)
        await context.delete()
        return

    if photo:
        if not custom_emoji:
            await context.edit("出错了呜呜呜 ~ 目标不是贴纸 。")
            sleep(2)
            await context.delete()
            return

        if not animated:
            await context.edit("正在转换...\n█████████90%")
            image = await resize_image(photo)
            filename = "sticker"+str(random())+".png"
            image.save(filename, "PNG")
        else:
            await context.edit("出错了呜呜呜 ~ 目标不是**静态**贴纸 。")
            sleep(2)
            await context.delete()
            return
        await context.edit("正在上传...\n██████████99%")
        await bot.send_file(context.chat_id,filename)
        try:
            await context.delete()
        except:
            pass
        try:
            remove(filename)
        except:
            pass
        try:
            remove("AnimatedSticker.tgs")
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
