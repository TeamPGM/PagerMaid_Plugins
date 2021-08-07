""" PagerMaid module for channel help. """
from asyncio import sleep
from random import uniform
from telethon.errors.rpcerrorlist import FloodWaitError
from pagermaid import redis, log, redis_status
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener


@listener(is_plugin=False, outgoing=True, command=alias_command('shift'),
          description='开启转发频道新消息功能，需要 Redis',
          parameters="set <from channel> <to channel> 自动转发频道新消息（可以使用频道用户名或者 id）\n"
                     "del <from channel> 删除转发\n"
                     "backup <from channel> <to channel> 备份频道（可以使用频道用户名或者 id）")
async def shift_set(context):
    if not redis_status():
        await context.edit(f"{lang('error_prefix')}{lang('redis_dis')}")
        return
    if not 1 < len(context.parameter) < 4:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    if context.parameter[0] == "set":
        if len(context.parameter) != 3:
            await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
            return
        # 检查来源频道
        try:
            channel = await context.client.get_entity(int(context.parameter[1]))
            if not channel.broadcast:
                await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                return
            channel = int(f'-100{channel.id}')
        except Exception:
            try:
                channel = await context.client.get_entity(context.parameter[1])
                if not channel.broadcast:
                    await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                    return
                channel = int(f'-100{channel.id}')
            except Exception:
                await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                return
        if channel in [-1001441461877]:
            await context.edit('出错了呜呜呜 ~ 此对话位于白名单中。')
            return
        # 检查目标频道
        try:
            to = int(context.parameter[2])
        except Exception:
            try:
                to = await context.client.get_entity(context.parameter[2])
                if to.broadcast or to.gigagroup or to.megagroup:
                    to = int(f'-100{to.id}')
                else:
                    to = to.id
            except Exception:
                await context.edit("出错了呜呜呜 ~ 无法识别的目标对话。")
                return
        if to in [-1001441461877]:
            await context.edit('出错了呜呜呜 ~ 此对话位于白名单中。')
            return
        redis.set("shift." + str(channel), f"{to}")
        await context.edit(f"已成功配置将对话 {channel} 的新消息转发到 {to} 。")
        await log(f"已成功配置将对话 {channel} 的新消息转发到 {to} 。")
    elif context.parameter[0] == "del":
        if len(context.parameter) != 2:
            await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
            return
        # 检查来源频道
        try:
            channel = int(context.parameter[1])
        except Exception:
            try:
                channel = (await context.client.get_entity(context.parameter[1])).id
                if channel.broadcast or channel.gigagroup or channel.megagroup:
                    channel = int(f'-100{channel.id}')
            except Exception:
                await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                return
        try:
            redis.delete("shift." + str(channel))
        except:
            await context.edit('emm...当前对话不存在于自动转发列表中。')
            return
        await context.edit(f"已成功关闭对话 {str(channel)} 的自动转发功能。")
        await log(f"已成功关闭对话 {str(channel)} 的自动转发功能。")
    elif context.parameter[0] == "backup":
        if len(context.parameter) != 3:
            await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
            return
        # 检查来源频道
        try:
            channel = await context.client.get_entity(int(context.parameter[1]))
            if not channel.broadcast:
                await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                return
            channel = int(f'-100{channel.id}')
        except Exception:
            try:
                channel = await context.client.get_entity(context.parameter[1])
                if not channel.broadcast:
                    await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                    return
                channel = int(f'-100{channel.id}')
            except Exception:
                await context.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
                return
        if channel in [-1001441461877]:
            await context.edit('出错了呜呜呜 ~ 此对话位于白名单中。')
            return
        # 检查目标频道
        try:
            to = int(context.parameter[2])
        except Exception:
            try:
                to = await context.client.get_entity(context.parameter[2])
                if to.broadcast or to.gigagroup or to.megagroup:
                    to = int(f'-100{to.id}')
                else:
                    to = to.id
            except Exception:
                await context.edit("出错了呜呜呜 ~ 无法识别的目标对话。")
                return
        if to in [-1001441461877]:
            await context.edit('出错了呜呜呜 ~ 此对话位于白名单中。')
            return
        # 开始遍历消息
        await context.edit(f'开始备份频道 {channel} 到 {to} 。')
        async for msg in context.client.iter_messages(int(channel), reverse=True):
            await sleep(uniform(0.5, 1.0))
            try:
                await forward_msg(context, msg, to)
            except BaseException:
                pass
        await context.edit(f'备份频道 {channel} 到 {to} 已完成。')
    else:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return


@listener(is_plugin=False, incoming=True, ignore_edited=True)
async def shift_channel_message(context):
    """ Event handler to auto forward channel messages. """
    if not redis_status():
        return
    if not redis.get("shift." + str(context.chat_id)):
        return
    if context.chat_id in [-1001441461877]:
        return
    cid = int(redis.get("shift." + str(context.chat_id)).decode())
    try:
        await context.forward_to(cid)
    except Exception as e:
        pass


async def forward_msg(context, msg, cid):
    try:
        await msg.forward_to(cid)
    except FloodWaitError as e:
        await context.edit(f'触发 Flood ，暂停 {e.seconds + uniform(0.5, 1.0)} 秒。')
        try:
            await sleep(e.seconds + uniform(0.5, 1.0))
        except Exception as e:
            print(f"Wait flood error: {e}")
            return
        await forward_msg(context, msg, cid)
