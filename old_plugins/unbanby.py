from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid import version
from telethon.tl.types import ChannelParticipantsKicked, ChannelParticipantsAdmins
from telethon.errors.rpcerrorlist import UserAdminInvalidError, ChatAdminRequiredError, FloodWaitError
from asyncio import sleep
from random import uniform


@listener(is_plugin=False, outgoing=True, command=alias_command("unbanby"),
          description='查询/解除群组中被所回复用户所封禁的用户。',
          parameters="<true>")
async def unban_by_bot(context):
    if not context.is_group:
        await context.edit('请在群组中运行。')
        return
    reply = await context.get_reply_message()
    if not reply:
        await context.edit('请回复一个用户。')
        return
    # 读取模式
    unban_mode = False
    if len(context.parameter) == 1:
        unban_mode = True
    text = f'查找被 Ta 封禁的用户中。'
    if unban_mode:
        text += '\n移除中。。。'
    await context.edit(text)
    # 读取权限
    count, members, members_count = 0, 0, 0
    admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
    if context.sender in admins:
        user = admins[admins.index(context.sender)]
        if not user.participant.admin_rights.ban_users:
            await context.edit('无封禁用户权限，停止查询。')
            return
    # 遍历列表
    async for x in context.client.iter_participants(context.chat, filter=ChannelParticipantsKicked):
        members += 1
        if x.participant.kicked_by == reply.sender_id:
            count += 1
            if unban_mode:
                try:
                    await context.client.edit_permissions(context.chat, x)
                except FloodWaitError as e:
                    # Wait flood secs
                    await context.edit(f'触发 Flood ，暂停 {e.seconds + uniform(0.5, 1.0)} 秒。')
                    try:
                        await sleep(e.seconds + uniform(0.5, 1.0))
                    except Exception as e:
                        print(f"Wait flood error: {e}")
                        return
                except UserAdminInvalidError:
                    await context.edit('无管理员权限，停止查询。')
                    return
                except ChatAdminRequiredError:
                    await context.edit('无管理员权限，停止查询。')
                    return
        # 每一百人修改一次
        if members == 100:
            members_count += 1
            members = 0
            await context.edit(text + f'\n已查找 {members_count * 100} 人。')
    text = ''
    if count > 0:
        text += f'查找到了 {count} 个被 Ta 封禁的用户。\n'
        if unban_mode:
            text += '解除完毕。'
        else:
            text += f'使用 `-unbanby yes` 开始解除封禁'
    else:
        text = f'没有发现被 Ta 封禁的用户呢。'
    await context.edit(text)
