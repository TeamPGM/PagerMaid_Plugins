""" PagerMaid module to anti channel msg. """
from telethon.errors import ChatAdminRequiredError
from telethon.tl.types import Channel, ChatBannedRights
from telethon.tl.functions.channels import GetFullChannelRequest, EditBannedRequest
from pagermaid import redis, log, redis_status, bot, user_id
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener


@listener(is_plugin=False, outgoing=True, command=alias_command('antichannelmsg'),
          description='开启对话的自动删除频道消息并且封禁频道功能，需要 Redis',
          parameters="<true|false|add <cid>|status>")
async def anti_channel_msg(context):
    if not redis_status():
        await context.edit(f"{lang('error_prefix')}{lang('redis_dis')}")
        return
    if context.chat_id == user_id or not context.is_group:
        await context.edit(lang('ghost_e_mark'))
        return
    if len(context.parameter) == 0:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    if context.parameter[0] == "true":
        data = await bot(GetFullChannelRequest(context.chat_id))
        if not data.full_chat.linked_chat_id:
            return await context.edit("当前群组未链接到频道，无法开启此功能。")
        redis.set("antichannelmsg." + str(context.chat_id), f"{data.full_chat.linked_chat_id}")
        await context.edit(f"已成功开启群组 {str(context.chat_id)} 的自动删除频道消息并且封禁频道功能。")
        await log(f"已成功开启群组 {str(context.chat_id)} 的自动删除频道消息并且封禁频道功能。")
    elif context.parameter[0] == "false":
        try:
            redis.delete("antichannelmsg." + str(context.chat_id))
        except:
            await context.edit('emm...当前对话不存在于自动删除频道消息并且封禁频道功能列表中。')
            return
        await context.edit(f"已成功关闭群组 {str(context.chat_id)} 的自动删除频道消息并且封禁频道功能。")
        await log(f"已成功关闭群组 {str(context.chat_id)} 的自动删除频道消息并且封禁频道功能。")
    elif context.parameter[0] == "add":
        data = redis.get("antichannelmsg." + str(context.chat_id))
        if not data:
            return await context.edit("emm...当前对话不存在于自动删除频道消息并且封禁频道功能列表中。")
        data = data.decode().split(" ")
        try:
            chat_id = context.parameter[1]
            channel_data = await bot(GetFullChannelRequest(int(chat_id)))  # noqa
        except TypeError:
            return await context.edit("频道 id 错误")
        except ValueError:
            return await context.edit("频道 id 不是 -100 开头的数字")
        except IndexError:
            return await context.edit("没有指定频道 id")
        data.append(str(channel_data.full_chat.id))
        redis.set("antichannelmsg." + str(context.chat_id), " ".join(data))
        await context.edit("添加频道到白名单成功。")
    elif context.parameter[0] == "status":
        if redis.get("antichannelmsg." + str(context.chat_id)):
            await context.edit('当前对话存在于自动删除频道消息并且封禁频道功能列表中。')
        else:
            await context.edit('当前对话不存在于自动删除频道消息并且封禁频道功能列表中。')
    else:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")


@listener(is_plugin=False, incoming=True, outgoing=False, ignore_edited=True)
async def auto_process_channel_msg(context):
    """ Event handler to delete channel messages and ban channel. """
    if not redis_status():
        return
    if not context.is_group:
        return
    # 匿名管理员
    if not context.sender:
        return
    data = redis.get("antichannelmsg." + str(context.chat_id))
    if not data:
        return
    try:
        if not isinstance(context.sender, Channel):
            return
        data = data.decode().split(" ")
        # 白名单
        if str(context.sender.id) in data:
            return
        # 删除消息,封禁频道
        try:
            await context.delete()
            entity = await context.client.get_input_entity(context.chat_id)
            user = await context.client.get_input_entity(context.sender.id)
            await context.client(EditBannedRequest(
                channel=entity,
                participant=user,
                banned_rights=ChatBannedRights(
                    until_date=None, view_messages=True)
            ))
        except ChatAdminRequiredError:
            redis.delete("antichannelmsg." + str(context.chat_id))
    except:
        return
    try:
        await context.unpin()
    except ChatAdminRequiredError:
        redis.delete("antichannelmsg." + str(context.chat_id))
    except:
        pass
