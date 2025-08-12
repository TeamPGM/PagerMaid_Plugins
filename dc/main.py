from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import MessageEntityMentionName, ChatPhotoEmpty, User, Chat, Channel
from struct import error as StructError
from telethon.utils import get_peer_id

from pagermaid.config import Config
from pagermaid.utils import lang
from pagermaid.listener import listener

DC_LOCATIONS = {
    1: "美国 迈阿密",
    2: "荷兰 阿姆斯特丹",
    3: "美国 迈阿密",
    4: "荷兰 阿姆斯特丹",
    5: "新加坡",
}


def _format_dc_info(entity):
    """Formats the DC information string from a user or chat entity."""
    if not entity.photo or isinstance(entity.photo, ChatPhotoEmpty):
        if isinstance(entity, User):
            return "[dc] 目标用户没有头像或头像对我不可见。"
        if isinstance(entity, Channel):
            return "[dc] 当前频道没有头像。" if entity.broadcast else "[dc] 当前群组没有头像。"
        if isinstance(entity, Chat):
            return "[dc] 当前群组没有头像。"
        # Fallback
        return "[dc] 当前对话没有头像或头像对我不可见。"

    dc_id = entity.photo.dc_id
    location = DC_LOCATIONS.get(dc_id, "未知")

    name = ""
    if isinstance(entity, User):
        name = entity.first_name
        if entity.last_name:
            name = f"{name} {entity.last_name}"
    else:  # Chat or Channel
        name = entity.title

    return f"**{name}** 所在数据中心为: **DC{dc_id} ({location})**"


@listener(
    command='dc',
    description="获取指定用户或当前群组/频道的 DC",
    parameters="<username/id> (可选)",
)
async def dc(context):
    if len(context.parameter) > 1:
        return await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")

    if not Config.SILENT:
        await context.edit(lang('profile_process'))

    try:
        entity = None
        if context.reply_to_msg_id:
            reply_message = await context.get_reply_message()
            if not reply_message:
                return await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")

            user_id = None
            if reply_message.fwd_from:
                if reply_message.fwd_from.from_id:
                    user_id = get_peer_id(reply_message.fwd_from.from_id)
                else:
                    return await context.edit("[dc] 无法获取匿名转发来源的 DC 信息。")
            else:
                user_id = reply_message.sender_id

            if not user_id:
                return await context.edit("[dc] 无法获取到回复消息的发送者。")

            entity = await context.client.get_entity(user_id)

        elif context.parameter:
            user_input = context.parameter[0]
            # Try to get entity from mention first
            if context.message.entities:
                for msg_entity in context.message.entities:
                    if isinstance(msg_entity, MessageEntityMentionName):
                        entity = await context.client.get_entity(msg_entity.user_id)
                        break
            if not entity:
                entity = await context.client.get_entity(user_input)
        else:
            entity = await context.get_chat()

        if not entity:
            return await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")

        # For users, we need GetFullUserRequest to get the photo dc_id reliably
        if isinstance(entity, User):
            full_user = await context.client(GetFullUserRequest(entity.id))
            entity = full_user.users[0]

        message = _format_dc_info(entity)
        await context.edit(message)

    except Exception as e:
        error_str = str(e)
        if "Cannot find any entity corresponding to" in error_str:
            await context.edit(f"{lang('error_prefix')}{lang('profile_e_no')}")
        elif "No user has" in error_str:
            await context.edit(f"{lang('error_prefix')}{lang('profile_e_nou')}")
        elif "Could not find the input entity for" in error_str or isinstance(e, StructError):
            await context.edit(f"{lang('error_prefix')}{lang('profile_e_nof')}")
        elif isinstance(e, OverflowError):
            await context.edit(f"{lang('error_prefix')}{lang('profile_e_long')}")
        elif isinstance(e, IndexError):  # From full_user.users[0]
            await context.edit("[dc] 无法获取该用户的完整信息。")
        else:
            await context.edit(f"{lang('error_prefix')}获取 DC 信息时出现未知错误: {e}")
