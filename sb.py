from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import lang, alias_command
from telethon.tl.functions.messages import GetCommonChatsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import MessageEntityMentionName
from telethon.errors.rpcerrorlist import UserAdminInvalidError, ChatAdminRequiredError, FloodWaitError
from asyncio import sleep
from random import uniform


def mention_user(user):
    first_name = user.first_name.replace("\u2060", "")
    return f'[{first_name}](tg://user?id={user.id})'


def mention_group(chat):
    try:
        if chat.username:
            if chat.username:
                text = f'[{chat.title}](https://t.me/{chat.username})'
            else:
                text = f'`{chat.title}`'
        else:
            text = f'`{chat.title}`'
    except AttributeError:
        text = f'`{chat.title}`'
    return text


@listener(is_plugin=False, outgoing=True, command=alias_command("sb"),
          description='在自己拥有管理员权限的共同群组中封禁一位用户。',
          parameters="<reply|id|username>")
async def span_ban(context):
    if context.reply_to_msg_id:
        reply_message = await context.get_reply_message()
        user = reply_message.from_id
        target_user = await context.client(GetFullUserRequest(user))
    else:
        if len(context.parameter) == 1:
            user = context.parameter[0]
            if user.isnumeric():
                user = int(user)
        else:
            await context.edit('无法获取到任何用户。')
            return
        if context.message.entities is not None:
            if isinstance(context.message.entities[0], MessageEntityMentionName):
                user = context.message.entities[0].user_id
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
    myself = await context.client.get_me()
    self_user_id = myself.id
    if target_user.user.id == self_user_id:
        await context.edit('不可以回复自己哦。')
        return
    result = await context.client(GetCommonChatsRequest(user_id=target_user, max_id=0, limit=100))
    count = 0
    groups = []
    for i in result.chats:
        try:
            await context.client.edit_permissions(i.id, target_user, view_messages=False)
            groups.append(mention_group(i))
            count += 1
        except FloodWaitError as e:
            # Wait flood secs
            await context.edit(f'触发 Flood ，暂停 {e.seconds + uniform(0.5, 1.0)} 秒。')
            try:
                await sleep(e.seconds + uniform(0.5, 1.0))
            except Exception as e:
                print(f"Wait flood error: {e}")
                return
        except UserAdminInvalidError:
            pass
        except ChatAdminRequiredError:
            pass
    if count == 0:
        text = f'没有在任何群封禁用户 {mention_user(target_user.user)}'
    else:
        text = f'在 {count} 个群封禁了用户 {mention_user(target_user.user)}'
    await context.edit(text)
    if len(groups) > 0:
        groups = '\n受影响的群组：' + "\n".join(groups)
    else:
        groups = ''
    await log(f'{text}\nuid: `{target_user.user.id}` {groups}')
