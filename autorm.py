""" Remove Sent Msg After A Specified Time. """

# By tg @fruitymelon
# extra requirements: dateparser
import asyncio, time, traceback, sys
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


offset = local_time_offset() // 3600
sign = "+" if offset >= 0 else "-"
offset = abs(offset)
offset_str = str(offset)
offset_str = offset_str if len(offset_str) == 2 else f"0{offset_str}"

settings = {'TIMEZONE': f'{sign}{offset_str}00'}

all_chat = False
all_chat_delta = None
chats = []
times = []

helpmsg = """
在指定的时间后删除自己的消息。
默认在当前群聊中启用，也可以设置为全部私聊、群聊和频道通用。重叠时，前者优先级更高。
PagerMaid 重启后将失效。

i.e.
-autorm 4 seconds
-autorm 1 minutes
-autorm global 1 minutes

取消删除自己的消息：

取消当前群 -autorm cancel
取消全局 -autorm global cancel
取消所有群和全局 -autorm cancelall
"""


@listener(outgoing=True, ignore_edited=True)
async def remove_message(context):
    """ Event handler to infinitely remove messages. """
    try:
        text = context.message.text if context.message.text else ""
        chat_id = context.chat_id
        if chats.count(chat_id) != 0:
            index = chats.index(chat_id)
            delta = times[index]
            if text.startswith("-autorm"):
                context.arguments = text.lstrip("-autorm").lstrip()
                await autorm(context)
            if text.startswith(f"-{alias_command('dme')}"):
                return
            await asyncio.sleep(delta)
            await context.delete()
            return
        elif all_chat:
            delta = all_chat_delta
            if text.startswith("-autorm"):
                context.arguments = text.lstrip("-autorm").lstrip()
                await autorm(context)
            if text.startswith(f"-{alias_command('dme')}"):
                return
            await asyncio.sleep(delta)
            await context.delete()
            return
    except Exception as e:
        try:
            await sendmsg(context, await context.get_chat(), str(e))
        except ValueError:
            pass


@listener(is_plugin=True, outgoing=True, command=alias_command("autorm"),
          diagnostics=True, ignore_edited=False,
          description=helpmsg,
          parameters="<time>")
async def autorm_wrap(context):
    return await autorm(context)


async def autorm(context):
    try:
        global all_chat, all_chat_delta, chats, times
        chat = await context.get_chat()
        chat_id = context.chat_id

        args = context.arguments if context.arguments is not None else ""
        args = args.strip()

        if len(args) == 0:
            await edit(context, "参数不能为空。使用 -help autorm 以查看帮助。")
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

        if args.startswith("global"):
            time_str = args[7:].strip()
            if time_str.startswith("cancel"):
                if all_chat == False:
                    await edit(context, "当前未开启全部群自动删除消息。")
                else:
                    all_chat = False
                    all_chat_delta = None
                    await edit(context, "成功为所有群取消自动删除消息。")
                return

            dt = dateparser.parse(time_str, settings=settings)
            if dt is None:
                await edit(context, "无法解析所指定的时间长度。")
                return

            delta = time.time() - dt.timestamp()
            if delta <= 3:
                await edit(context, "所指定的时间长度过短。")
                return

            all_chat = True
            all_chat_delta = delta
            await edit(context, "已成功启用全局自动删除消息。")
            return

        if args.startswith("cancel"):
            if args.startswith("cancelall"):
                if all_chat == False and len(chats) == 0:
                    await edit(context, "似乎没有什么可以取消的。")
                else:
                    all_chat = False
                    all_chat_delta = None
                    chats = []
                    times = []
                    await edit(context, "已取消全部先前创建的自动删除消息服务。")
                return
            if chats.count(chat_id) == 0:
                await edit(context, "当前群未开启自动删除消息。")
                return
            index = chats.index(chat_id)
            chats.pop(index)
            times.pop(index)
            await edit(context, "成功为当前群取消自动删除消息。")
            return
        dt = dateparser.parse(args, settings=settings)

        if dt is None:
            await edit(context, "无法解析所指定的时间长度。")
            return

        delta = time.time() - dt.timestamp()

        if delta <= 3:
            await edit(context, "所指定的时间长度过短。")
            return

        if chats.count(chat_id) != 0:
            index = chats.index(chat_id)
            chats.pop(index)
            times.pop(index)
        chats.append(chat_id)
        times.append(delta)
        await edit(context, "成功在当前群启用自动删除消息。")
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
            return await sendmsg(context, chat, f"{text} {str(e)} {stack}")
        else:
            return context


async def sendmsg(context, chat, origin_text):
    text = origin_text.strip()
    msg = await context.client.send_message(chat, text)
    return msg
