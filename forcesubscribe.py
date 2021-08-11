from pagermaid import bot, redis, redis_status
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener
from asyncio import sleep
from telethon.events.chataction import ChatAction
from telethon.tl.custom.message import Message
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors.rpcerrorlist import UserNotParticipantError, ChatAdminRequiredError
from telethon import events


@bot.on(events.ChatAction())
async def force_subscribe_join(event: ChatAction.Event):
    if not redis_status():
        return
    if not (event.user_joined or event.user_added):
        return
    join_chat = redis.get(f"sub.chat_id.{event.chat_id}")
    if not join_chat:
        return
    else:
        join_chat = join_chat.decode()
    user = await event.get_user()
    if user.bot:
        return
    if redis.get(f"sub.chat_id.{event.chat_id}.{user.id}"):
        return
    try:
        try:
            await bot(GetParticipantRequest(join_chat, user.id))
        except ValueError:
            user_input = await event.get_input_user()
            await bot(GetParticipantRequest(join_chat, user_input))
        redis.set(f'sub.chat_id.{event.chat_id}.{user.id}', 'true')
        redis.expire(f'sub.chat_id.{event.chat_id}.{user.id}', 3600)
    except UserNotParticipantError:
        msg = await event.reply(f'[{user.first_name}](tg://user?id={user.id}) 您需要先加入频道 @{join_chat} 才能发言。')
        await sleep(30)
        await msg.delete()
    except ChatAdminRequiredError:
        redis.delete(f"sub.chat_id.{event.chat_id}")


@listener(is_plugin=True, incoming=True, ignore_edited=True)
async def force_subscribe_msg(context: Message):
    if not redis_status():
        return
    join_chat = redis.get(f"sub.chat_id.{context.chat_id}")
    if not join_chat:
        return
    if redis.get(f"sub.chat_id.{context.chat_id}.{context.sender_id}"):
        return
    else:
        join_chat = join_chat.decode()
    try:
        if context.sender.bot:
            return
    except AttributeError:
        return
    try:
        try:
            await bot(GetParticipantRequest(join_chat, context.sender_id))
        except ValueError:
            await bot.get_participants(context.chat)
            await bot(GetParticipantRequest(join_chat, context.sender_id))
        redis.set(f'sub.chat_id.{context.chat_id}.{context.sender_id}', 'true')
        redis.expire(f'sub.chat_id.{context.chat_id}.{context.sender_id}', 3600)
    except UserNotParticipantError:
        try:
            await context.delete()
            try:
                msg = await bot.send_message(context.chat_id,
                                             f'[{context.sender.first_name}](tg://user?id={context.sender_id}) '
                                             f'您需要先加入频道 @{join_chat} 才能发言。')
                await sleep(15)
                await msg.delete()
            except ValueError:
                pass
        except ChatAdminRequiredError:
            redis.delete(f"sub.chat_id.{context.chat_id}")
    except ChatAdminRequiredError:
        redis.delete(f"sub.chat_id.{context.chat_id}")


@listener(is_plugin=True, outgoing=True, command=alias_command('forcesub'),
          description='自动删除未关注指定公开频道的用户的发言。',
          parameters="<username|false|status>")
async def force_sub(context):
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
        redis.delete(f"sub.chat_id.{context.chat_id}")
        await context.edit(f'成功关闭强制关注频道功能。')
    elif context.parameter[0] == "status":
        if redis.get(f"sub.chat_id.{context.chat_id}"):
            join_chat = redis.get(f"sub.chat_id.{context.chat_id}").decode()
            await context.edit(f'当前群组强制需要关注频道的频道为： @{join_chat} 。')
        else:
            await context.edit('当前群组未开启强制关注频道功能。')
    else:
        if context.chat_id == self_user_id:
            await context.edit(lang('ghost_e_mark'))
            return
        sub_channel = context.parameter[0].replace('@', '')
        try:
            await context.client.get_participants(sub_channel, filter=ChannelParticipantsAdmins)
        except:
            await context.edit(f'设置失败：不是频道 @{sub_channel} 的管理员。')
            return
        redis.set(f"sub.chat_id.{context.chat_id}", sub_channel)
        await context.edit(f'已设置当前群组强制需要关注频道的频道为： @{sub_channel} 。')
