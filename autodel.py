""" Remove Someone's Msg After A Specified Time. """
# extra requirements: dateparser, redis

import time
import traceback

from asyncio import sleep
from telethon.tl.types import PeerUser
from telethon.tl.custom import Message
from pagermaid import redis, redis_status, version
from pagermaid.listener import listener
from pagermaid.utils import alias_command, pip_install

pip_install("dateparser")

import dateparser


# https://stackoverflow.com/questions/1111056/get-time-zone-information-of-the-system-in-python
def local_time_offset(t=None):
    """Return offset of local zone from GMT, either at present or at time t."""
    # python2.3 localtime() can't take None
    if t is None:
        t = time.time()

    if time.localtime(t).tm_isdst and time.daylight:
        return -time.altzone
    else:
        return -time.timezone


@listener(incoming=True, ignore_edited=True)
async def remove_others_message(context):
    """ Event handler to infinitely remove messages. """
    if not redis_status():
        return
    if not context.is_group:
        return
    chat_id = context.chat_id
    if not isinstance(context.from_id, PeerUser):
        return
    uid = context.from_id.user_id
    mid = context.id
    data = redis.get(f"autodel.{chat_id}.{uid}")
    if data:
        delta = float(data.decode())
        await sleep(delta)
        # 检查消息是否仍然存在
        chat = await context.get_chat()
        msg = await context.client.get_messages(chat, ids=mid)
        if msg:
            try:
                await context.delete()
            except Exception as e:
                try:
                    await send_msg(context, await context.get_chat(), str(e))
                except ValueError:
                    pass


@listener(is_plugin=True, outgoing=True, command=alias_command("autodel"),
          diagnostics=True,
          description="""
在指定的时间后删除所回复用户发送的消息。只对当前群组有效。

i.e.
-autodel 4 seconds
-autodel 1 minutes
-autodel 1 hours

取消删除消息：

-autodel cancel
""",
          parameters="<time>")
async def auto_del(context: Message):
    try:
        chat_id = context.chat_id
        # 读取参数
        args = context.arguments if context.arguments is not None else ""
        args = args.strip()
        reply = await context.get_reply_message()

        if not redis_status():
            await edit(context, f"出错了呜呜呜 ~ 数据库离线。")
            return
        if not reply:
            await edit(context, f"出错了呜呜呜 ~ 没有回复一条消息。")
            return
        if not reply.sender:
            await edit(context, f"出错了呜呜呜 ~ 无法获取回复的用户。")
            return
        if not context.is_group:
            await edit(context, f"出错了呜呜呜 ~ 没有在群组中执行。")
            return
        uid = reply.sender.id
        # 处理参数
        if len(args) == 0:
            await edit(context, "参数不能为空。使用 -help autodel 以查看帮助。")
            return
        if args.find("cancel") == -1 and not any(char.isdigit() for char in args):
            await edit(context, "指定的参数中似乎没有时间长度。")
            return
        if args.find("cancel") == -1 and all(char.isdigit() for char in args):
            await edit(context, "请指定时间长度的单位。")
            return
        if args.find(":") != -1 or args.find("-") != -1:
            await edit(context, "请使用相对时间长度，而非绝对时间长度：不能含 : 或 -。")
            return
        # 处理取消
        if args.startswith("cancel"):
            if redis.get(f"autodel.{chat_id}.{uid}"):
                redis.delete(f"autodel.{chat_id}.{uid}")
                await context.edit('成功在当前群取消定时删除所回复对象的消息。')
            else:
                await context.edit('未在当前群启用定时删除所回复对象的消息。')
            return
        # 解析时间长度
        offset = local_time_offset() // 3600
        sign = "+" if offset >= 0 else "-"
        offset = abs(offset)
        offset_str = str(offset)
        offset_str = offset_str if len(offset_str) == 2 else f"0{offset_str}"

        settings = {'TIMEZONE': f'{sign}{offset_str}00'}
        dt = dateparser.parse(args, settings=settings)

        if dt is None:
            await edit(context, "无法解析所指定的时间长度。")
            return

        delta = time.time() - dt.timestamp()
        if delta <= 3:
            await edit(context, "所指定的时间长度过短。")
            return
        # 写入数据库
        redis.set(f"autodel.{chat_id}.{uid}", f"{delta}")
        await edit(context, "成功在当前群启用定时删除所回复对象的消息。")
        return
    except Exception as e:
        await edit(context, f"Error: {str(e)}")
    return


async def edit(context, text):
    chat = await context.get_chat()
    try:
        return await context.edit(text)
    except Exception as e:
        if str(e).find("you can't do that operation") == -1:
            stack = "\n".join(traceback.format_stack())
            return await send_msg(context, chat, f"{text} {str(e)} {stack}")
        else:
            return context


async def send_msg(context, chat, origin_text):
    text = origin_text.strip()
    msg = await context.client.send_message(chat, text)
    return msg
