from pagermaid.listener import listener
from pagermaid.utils import alias_command
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors.rpcerrorlist import UserAdminInvalidError, ChatAdminRequiredError, FloodWaitError
from asyncio import sleep
from random import uniform


def eval_time(context, msg, day):
    now = context.date
    old = msg.date
    days = (now - old).days
    if days < day:
        return False
    else:
        return True


@listener(is_plugin=False, outgoing=True, command=alias_command("fuckmember"),
          description='查找/清理群组中所有潜水超过 n 天的成员。（n>=7）。',
          parameters="<day> <true>")
async def fuck_member(context):
    if not context.is_group:
        await context.edit('请在群组中运行。')
        return
    # 读取天数
    text = ''
    kick_mode = False
    if len(context.parameter) == 1 or len(context.parameter) == 2:
        if len(context.parameter) == 2:
            kick_mode = True
        try:
            day = int(context.parameter[0])
            if day < 7:
                day = 7
                text += '由于输入的数据过小，时间自动设置为 7 天。\n'
        except (KeyError, ValueError):
            day = 7
            text += '由于输入的数据错误，时间自动设置为 7 天。\n'
    else:
        day = 7
        text += '由于未输入数据，时间自动设置为 7 天。\n'
    text += f'查找潜水超过 {day} 天的成员中。'
    if kick_mode:
        text += '\n移除中。。。'
    await context.edit(text)
    # 获取管理员
    msg, count, counts, members, members_count = 0, 0, 0, 0, 0
    admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
    async for x in context.client.iter_participants(context.chat):
        members += 1
        if x in admins:
            continue
        async for message in context.client.iter_messages(context.chat_id, limit=1, from_user=x):
            msg += 1
            time = eval_time(context, message, day)
            if time:
                count += 1
                if kick_mode:
                    try:
                        await context.client.kick_participant(context.chat_id, x)
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
        if msg == 1:
            msg = 0
        else:
            counts += 1
            if kick_mode:
                try:
                    await context.client.kick_participant(context.chat_id, x)
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
        text += f'查找到了 {count} 个未发言超过 {day} 天的群成员。\n'
    if counts > 0:
        text += f'查找到了 {counts} 个从未发言的群成员。\n'
    all_count = count + counts
    if all_count > 0:
        text += f'总共查找了 {all_count} 个群成员。\n'
    if not text == '':
        if kick_mode:
            text += '清理完毕。'
        else:
            text += f'使用 `-fuckmember {day} yes` 开始清理'
    else:
        text = f'没有发现潜水超过 {day} 天的群成员呢，大家都很活跃！'
    await context.edit(text)
