from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import MessageEntityMentionName, MessageEntityPhone, ChatPhotoEmpty
from struct import error as StructError

from pagermaid.config import Config
from pagermaid.utils import lang
from pagermaid.listener import listener


@listener(
    command='dc',
    description="获取指定用户或当前群组/频道的 DC",
    parameters="<username/id> (可选)",
)
async def dc(context):
    if len(context.parameter) > 1:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    if not Config.SILENT:
        await context.edit(lang('profile_process'))
    if context.reply_to_msg_id:
        reply_message = await context.get_reply_message()
        if not reply_message:
            return await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        
        user_id = reply_message.from_id
        if not user_id:
             # Should not happen, but as a safeguard
             return await context.edit("[dc] 无法获取到回复消息的发送者。")

        try:
            # First, assume it's a user
            target_user = await context.client(GetFullUserRequest(user_id))
            user_info = target_user.users[0]
            if isinstance(user_info.photo, ChatPhotoEmpty):
                return await context.edit("[dc] 目标用户没有头像。")
            await context.edit(f"**{user_info.first_name}** 所在数据中心为: **DC{user_info.photo.dc_id}**")
            return
        except (TypeError, ValueError):
            # If GetFullUserRequest fails, it might be a channel
            try:
                chat = await reply_message.get_chat()
                if not chat or not hasattr(chat, 'photo') or isinstance(chat.photo, ChatPhotoEmpty):
                    return await context.edit("[dc] 回复的消息所在对话需要先设置头像并且对我可见。")
                await context.edit(f"**{chat.title}** 所在数据中心为: **DC{chat.photo.dc_id}**")
                return
            except Exception:
                 return await context.edit("[dc] 无法获取该对象的 DC 信息。")
    else:
        if len(context.parameter) == 0:
            chat = await context.get_chat()
            if isinstance(chat.photo, ChatPhotoEmpty):
                return await context.edit("[dc] 当前群组/频道没有头像。")
            await context.edit(f"**{chat.title}** 所在数据中心为: **DC{chat.photo.dc_id}**")
            return

        user = None
        if context.message.entities:
            for entity in context.message.entities:
                if isinstance(entity, MessageEntityMentionName):
                    user = entity.user_id
                    break
                if isinstance(entity, MessageEntityPhone):
                    user = int(context.parameter[0])
                    break
        
        if not user:
            user = context.parameter[0]
            if user.isnumeric():
                user = int(user)

        if not user:
            await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
            return
        try:
            user_object = await context.client.get_entity(user)
            target_user = await context.client(GetFullUserRequest(user_object.id))
            user_info = target_user.users[0]
            if not user_info.photo:
                return await context.edit("[dc] 目标用户需要先设置头像并且对我可见。")
            await context.edit(f"**{user_info.first_name}** 所在数据中心为: **DC{user_info.photo.dc_id}**")
        except (TypeError, ValueError, OverflowError, StructError) as exception:
            if str(exception).startswith("Cannot find any entity corresponding to"):
                await context.edit(f"{lang('error_prefix')}{lang('profile_e_no')}")
                return
            if str(exception).startswith("No user has"):
                await context.edit(f"{lang('error_prefix')}{lang('profile_e_nou')}")
                return
            if str(exception).startswith("Could not find the input entity for") or isinstance(exception, StructError):
                await context.edit(f"{lang('error_prefix')}{lang('profile_e_nof')}")
                return
            if isinstance(exception, OverflowError):
                await context.edit(f"{lang('error_prefix')}{lang('profile_e_long')}")
                return
            raise exception
