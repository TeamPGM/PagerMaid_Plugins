import io
from redis.exceptions import ConnectionError
from requests import get
from os import remove
from telethon.tl.types import MessageMediaPhoto
from pagermaid import bot, redis, redis_status
from pagermaid.listener import listener
from pagermaid.utils import obtain_message, alias_command

try:
    import aiohttp, aiofiles
    pixiv_import = True
except ImportError:
    pixiv_import = False
p_headers = {
    "Referer": 'https://www.pixiv.net',
    'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 '
        'Safari/537.36',
}
p_original = ['i.pixiv.cat', 'i.pximg.net', 'pixiv.kadokawa.moe']


@listener(is_plugin=True, outgoing=True, command=alias_command("duckduckgo"),
          description="Duckduckgo 搜索",
          parameters="<query>")
async def baidu(context):
    await context.edit("获取中 . . .")
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message('/duckduckgo ' + message)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        duckduckgo_text = chat_response.text
    await context.edit(duckduckgo_text)


@listener(is_plugin=True, outgoing=True, command=alias_command("baidu"),
          description="百度搜索",
          parameters="<query>")
async def baidu(context):
    await context.edit("获取中 . . .")
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message('/baidu ' + message)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        baidu_text = chat_response.text
    await context.edit(baidu_text)


@listener(is_plugin=True, outgoing=True, command=alias_command("weather"),
          description="使用彩云天气 api 查询国内实时天气。",
          parameters="<位置>")
async def weather(context):
    await context.edit("获取中 . . .")
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message('/weather_api ' + message)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        weather_text = chat_response.text
    await context.edit(weather_text)


@listener(is_plugin=True, outgoing=True, command=alias_command("weather_pic"),
          description="使用彩云天气 api 查询国内实时天气。",
          parameters="<位置>")
async def weather(context):
    await context.edit("获取中 . . .")
    reply = await context.get_reply_message()
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message('/weather ' + message)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
    if reply:
        await context.respond(chat_response, reply_to=reply)
    else:
        await context.respond(chat_response)
    await context.delete()


@listener(is_plugin=True, outgoing=True, command=alias_command("pixiv"),
          description="查询插画信息 （或者回复一条消息）。使用 set [num] 更改镜像源，序号 2 为官方源， 3 为凯露自建源。异步下载需要依赖库 "
                      "aiohttp[speedups] 、 aiofiles",
          parameters="[<图片链接>] <图片序号>")
async def pixiv(context):
    await context.edit("获取中 . . .")
    if len(context.parameter) == 2:
        if context.parameter[0] == 'set':
            if not redis_status():
                await context.edit('redis 数据库离线 无法更改镜像源。')
                return
            else:
                try:
                    num = int(context.parameter[1])
                except ValueError:
                    await context.edit('镜像源序号错误。')
                    return
                if 0 < num < 4:
                    try:
                        redis.set("pixiv_num", num)
                    except ConnectionError:
                        await context.edit('redis 数据库离线 无法更改镜像源。')
                        return
                    await context.edit('镜像源已更改。')
                    return
                else:
                    await context.edit('镜像源序号错误。')
                    return
        else:
            pass
    if not redis_status():
        num = 3
    else:
        try:
            num = int(redis.get("pixiv_num").decode())
        except AttributeError:
            num = 3
        except ConnectionError:
            num = 3
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message('/pixiv_api ' + message)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        pixiv_text = chat_response.text
    pixiv_text = pixiv_text.replace('i.pixiv.cat', p_original[num - 1])
    pixiv_list = pixiv_text.split('|||||')
    if len(pixiv_list) == 2:
        pixiv_albums = pixiv_list[1].split('|||')
        pixiv_album = []
        if pixiv_import:
            await context.edit("调用异步下载图片中 . . .")
        else:
            await context.edit("下载图片中 . . .")
        if len(pixiv_albums) > 8:
            await context.edit('获取的图片数大于 8 ，将只发送前8张图片，下载图片中 . . .')
        for i in range(0, min(len(pixiv_albums), 8)):
            if not pixiv_import:
                r = get(pixiv_albums[i], headers=p_headers)
                with open("pixiv." + str(i) + ".jpg", "wb") as code:
                    code.write(r.content)
            else:
                async with aiohttp.ClientSession(headers=p_headers) as session:
                    response = await session.get(pixiv_albums[i])
                    content = await response.read()
                    async with aiofiles.open("pixiv." + str(i) + ".jpg", mode='wb') as code:
                        await code.write(content)
                        await code.close()
            pixiv_album.extend(["pixiv." + str(i) + ".jpg"])
        await context.client.send_file(context.chat_id, pixiv_album,
                                       caption=pixiv_list[0])
        await context.delete()
        for i in pixiv_album:
            try:
                remove(i)
            except:
                pass
    else:
        await context.edit(pixiv_text)


@listener(is_plugin=True, outgoing=True, command=alias_command("whatanime"),
          description="通过图片查找相似动漫。（需要回复图片）")
async def whatanime(context):
    reply = await context.get_reply_message()
    if reply is not None:
        if reply.media:
            if not isinstance(reply.media, MessageMediaPhoto):
                await context.edit("宁需要回复一张图片")
                return
        else:
            await context.edit("宁需要回复一张图片")
            return
    else:
        await context.edit("宁需要回复一张图片")
        return
    await context.edit("获取中。。。")
    async with bot.conversation('PagerMaid_Modify_bot') as conversation:
        await conversation.send_message(message='/whatanime_api', file=reply.photo)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        whatanime_text = chat_response.text
    whatanime_list = whatanime_text.split('|||')
    if len(whatanime_list) == 1:
        await context.edit(whatanime_text)
        return
    link = whatanime_list[0]
    name = whatanime_list[1]
    native = whatanime_list[2]
    episode = whatanime_list[3]
    alias = whatanime_list[4]
    r18 = whatanime_list[5]
    percent = whatanime_list[6]
    img = whatanime_list[7]
    video = whatanime_list[8]
    text = f'[{name}]({link}) （`{native}`）\n'
    if bool(episode):
        text += f'\n**集数：** `{episode}`'
    if bool(alias):
        text += f'\n**别名：** `{alias}`'
    if bool(r18):
        text += f'\n**R-18**'
    text += f'\n**相似度：** `{percent}`'

    r = get(img)
    photo = io.BytesIO(r.content)
    photo.name = f'{name}.png'
    msg = await context.client.send_file(context.chat_id,
                                         file=photo,
                                         caption=text,
                                         reply_to=reply.id)

    if not video == '':
        video_list = video.split('||')
        video = video_list[0]
        title = video_list[1]
        start = video_list[2]
        end = video_list[3]
        text = f'`{title}`\n\n`{start}` - `{end}`'
        await context.client.send_file(context.chat_id,
                                       video,
                                       caption=text,
                                       reply_to=msg.id)
    await context.delete()
