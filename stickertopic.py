from time import sleep
from os import remove
from io import BytesIO
from telethon.tl.types import DocumentAttributeFilename, MessageMediaPhoto, MessageMediaWebPage
from PIL import Image
from pagermaid import bot
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from random import random


@listener(outgoing=True, command=alias_command("stickertopic"),
          description="将你回复的静态贴纸转换为图片", parameters="<y/n>（是否发送原图，默认为n）")
async def stickertopic(context):
    try:
        if len(context.parameter) >= 1:
            if context.parameter[0][0].lower() == "y":
                as_file = True
            elif context.parameter[0][0].lower() == "n":
                as_file = False
            elif not context.parameter[0]:
                as_file = False
            else:
                raise IndexError
        else:
            as_file = False
    except:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    user = await bot.get_me()
    if not user.username:
        user.username = user.first_name
    message = await context.get_reply_message()
    custom_emoji = False
    animated = False
    await context.edit("开始转换...\n0%")
    if message and message.media:
        if isinstance(message.media, MessageMediaPhoto):
            photo = BytesIO()
            photo = await bot.download_media(message.photo, photo)
        elif isinstance(message.media, MessageMediaWebPage):
            await context.edit("出错了呜呜呜 ~ 目标不是贴纸 。")
            sleep(2)
            await context.delete()
            return
        elif "image" in message.media.document.mime_type.split('/'):
            photo = BytesIO()
            await context.edit("正在转换...\n████40%")
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
            await context.edit("正在转换...\n███████70%")
            image = Image.open(photo)
            filename = "sticker" + str(random())[2:] + ".png"
            image.save(filename, "PNG")
        else:
            await context.edit("出错了呜呜呜 ~ 目标不是**静态**贴纸 。")
            sleep(2)
            await context.delete()
            return
        await context.edit("正在上传...\n██████████99%")
        await bot.send_file(context.chat_id, filename, force_document=as_file)
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
