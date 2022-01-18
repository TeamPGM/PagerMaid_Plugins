from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import MessageEntityMentionName, MessageEntityPhone
from struct import error as StructError
from pagermaid import bot, log, silent, version
from pagermaid.utils import lang, alias_command
from pagermaid.listener import listener


@listener(is_plugin=False, outgoing=True, command=alias_command('dc'),
          description="获取指定用户的 DC",
          parameters="<username/id>")
async def dc(context):
    if len(context.parameter) > 1:
        await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        return
    if not silent:
        await context.edit(lang('profile_process'))
    if context.reply_to_msg_id:
        reply_message = await context.get_reply_message()
        if not reply_message:
            return await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
        user = reply_message.from_id
        try:
            target_user = await context.client(GetFullUserRequest(user))
        except TypeError:
            return await context.edit("[dc] 暂不支持频道。")
    else:
        if len(context.parameter) == 1:
            user = context.parameter[0]
            if user.isnumeric():
                user = int(user)
        else:
            user_object = await context.client.get_me()
            user = user_object.id
        if context.message.entities is not None:
            if isinstance(context.message.entities[0], MessageEntityMentionName):
                user = context.message.entities[0].user_id
            elif isinstance(context.message.entities[0], MessageEntityPhone):
                user = int(context.parameter[0])
            else:
                await context.edit(f"{lang('error_prefix')}{lang('arg_error')}")
                return
        try:
            user_object = await context.client.get_entity(user)
            target_user = await context.client(GetFullUserRequest(user_object.id))
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
    if not target_user.user.photo:
        return await context.edit("[dc] 需要先设置头像并且对我可见。")
    await context.edit(f"[dc] 所在数据中心为: **DC{target_user.user.photo.dc_id}**")
