""" PagerMaid module to anti channel pin. """
from telethon.errors import ChatAdminRequiredError
from telethon.tl.types import Channel
from asyncio import sleep
from pagermaid import redis, log, redis_status, version
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener


@listener(is_plugin=False, outgoing=True, command=alias_command('antichannelpin'),
          description='开启对话的自动取消频道置顶功能，需要 Redis',
          parameters="<true|false|status>")
async def antichannelpin(context):
    if not redis_status():
        await context.edit(f"{lang('error_prefix')}{lang('redis_dis')}")
        return
    if len(context.parameter) != 1:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    myself = await context.client.get_me()
    self_user_id = myself.id
    if context.parameter[0] == "true":
        if context.chat_id == self_user_id:
            await context.edit(lang('ghost_e_mark'))
            return
        redis.set("antichannelpin." + str(context.chat_id), "true")
        await context.edit(f"已成功开启群组 {str(context.chat_id)} 的自动取消频道置顶功能。")
        await log(f"已成功开启群组 {str(context.chat_id)} 的自动取消频道置顶功能。")
    elif context.parameter[0] == "false":
        if context.chat_id == self_user_id:
            await context.edit(lang('ghost_e_mark'))
            return
        try:
            redis.delete("antichannelpin." + str(context.chat_id))
        except:
            await context.edit('emm...当前对话不存在于自动取消频道置顶功能列表中。')
            return
        await context.edit(f"已成功关闭群组 {str(context.chat_id)} 的自动取消频道置顶功能。")
        await log(f"已成功关闭群组 {str(context.chat_id)} 的自动取消频道置顶功能。")
    elif context.parameter[0] == "status":
        if redis.get("antichannelpin." + str(context.chat_id)):
            await context.edit('当前对话存在于自动取消频道置顶功能列表中。')
        else:
            await context.edit('当前对话不存在于自动取消频道置顶功能列表中。')
    else:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")


@listener(is_plugin=False, incoming=True, ignore_edited=True)
async def unpin_link_channel_message(context):
    """ Event handler to unpin linked channel messages. """
    if not redis_status():
        return
    if not redis.get("antichannelpin." + str(context.chat_id)):
        return
    try:
        if not isinstance(context.sender, Channel):
            return
    except:
        return
    await sleep(1)
    try:
        await context.unpin()
    except ChatAdminRequiredError:
        redis.delete("antichannelpin." + str(context.chat_id))
    except:
        pass
