from pagermaid import bot, redis, redis_status, version
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener
from asyncio import sleep
from telethon.tl.custom.message import Message
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors.rpcerrorlist import UserNotParticipantError, ChatAdminRequiredError
from telethon.tl.types import ChannelParticipantsAdmins


@listener(is_plugin=True, incoming=True, ignore_edited=True)
async def force_group_msg(context: Message):
    if not redis_status():
        return
    join_chat = redis.get(f"group.chat_id.{context.chat_id}")
    if not join_chat:
        return
    if redis.get(f"group.chat_id.{context.chat_id}.{context.sender_id}"):
        return
    try:
        if context.sender.bot:
            pass
    except AttributeError:
        return
    try:
        try:
            await bot(GetParticipantRequest(context.chat, context.sender_id))
        except ValueError:
            await bot.get_participants(context.chat)
            await bot(GetParticipantRequest(context.chat, context.sender_id))
        redis.set(f'group.chat_id.{context.chat_id}.{context.sender_id}', 'true')
        redis.expire(f'group.chat_id.{context.chat_id}.{context.sender_id}', 3600)
    except UserNotParticipantError:
        try:
            reply = await context.get_reply_message()
            try:
                reply = reply.id
            except AttributeError:
                reply = None
            await context.delete()
            msg = await bot.send_message(context.chat_id,
                                         f'[{context.sender.first_name}](tg://user?id={context.sender_id}) '
                                         f'您需要先加入频道讨论群才能发言。',
                                         reply_to=reply)
            await sleep(5)
            await msg.delete()
        except ChatAdminRequiredError:
            redis.delete(f"group.chat_id.{context.chat_id}")
    except ChatAdminRequiredError:
        redis.delete(f"group.chat_id.{context.chat_id}")


@listener(is_plugin=True, outgoing=True, command=alias_command('forcegroup'),
          description='自动删除未加入频道讨论群用户的发言。',
          parameters="<true|false|status>")
async def force_group(context):
    if not redis_status():
        await context.edit(f"{lang('error_prefix')}{lang('redis_dis')}")
        return
    if len(context.parameter) != 1:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    myself = await context.client.get_me()
    self_user_id = myself.id
    if context.parameter[0] == "false":
        if context.chat_id == self_user_id:
            await context.edit(lang('ghost_e_mark'))
            return
        redis.delete(f"group.chat_id.{context.chat_id}")
        await context.edit(f'成功关闭强制加入频道讨论群功能。')
    elif context.parameter[0] == "status":
        if redis.get(f"group.chat_id.{context.chat_id}"):
            await context.edit(f'当前群组已开启强制加入频道讨论群功能。')
        else:
            await context.edit('当前群组未开启强制加入频道讨论群功能。')
    else:
        if context.chat_id == self_user_id:
            await context.edit(lang('ghost_e_mark'))
            return
        admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
        if context.sender in admins:
            user = admins[admins.index(context.sender)]
            if not user.participant.admin_rights.delete_messages:
                await context.edit('无删除消息权限，拒绝开启此功能。')
                return
        redis.set(f"group.chat_id.{context.chat_id}", 'true')
        await context.edit(f'成功在当前群组开启强制加入频道讨论群功能。')
