""" PagerMaid module to anti channel msg. """
from telethon.errors import ChatAdminRequiredError
from telethon.tl.types import Channel, ChatBannedRights
from telethon.tl.functions.channels import GetFullChannelRequest, EditBannedRequest
from pagermaid import redis, log, redis_status, bot, user_id, version
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener


@listener(is_plugin=False, outgoing=True, command=alias_command('antichannelmsg'),
          description='开启对话的自动删除频道消息并且封禁频道功能，需要 Redis',
          parameters="<true|false|add <cid>|filter <participants_count>|status>")
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
    elif context.parameter[0] == "filter":
        try:
            filter_int = int(context.parameter[1])
        except (IndexError, ValueError):
            return await context.edit("输入错误。")
        redis.set("antichannelmsg.filter:" + str(context.chat_id), str(filter_int))
        await context.edit(f"添加过滤成功，即群组 {str(context.chat_id)} 需要大于"
                           f" {str(filter_int)} 订阅人数的频道才能发言，否则会遭到删除并封禁。")
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
    filter_data = redis.get("antichannelmsg.filter:" + str(context.chat_id))
    if filter_data is not None:
        participants_count = redis.get("antichannelmsg.participants_count:" + str(context.chat_id))
        if participants_count is None:
            expire = 300
            try:
                channel_data = await bot(GetFullChannelRequest(int(context.sender.id)))
                participants_count = channel_data.full_chat.participants_count
                expire = 3600
            except:  # noqa
                participants_count = 0
            redis.set("antichannelmsg.participants_count:" + str(context.chat_id),
                      participants_count, ex=expire)
        else:
            try:
                participants_count = int(participants_count)
            except ValueError:
                participants_count = 0
        try:
            filter_int = int(filter_data)
        except ValueError:
            filter_int = -1
    try:
        if not isinstance(context.sender, Channel):
            return
        data = data.decode().split(" ")
        # 白名单
        if str(context.sender.id) in data:
            return
        # 频道订阅人数检测
        if filter_data is not None and (filter_int != -1 and participants_count >= filter_int):
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
