from pagermaid.listener import listener
from pagermaid.utils import alias_command
from telethon.tl.types import ChannelParticipantsAdmins


def eval_time(context, msg, day):
    now = context.date
    old = msg.date
    between = (now - old).seconds
    require_sec = day * 86400
    if between < require_sec:
        return None
    minute, sec = divmod(between, 60)
    hour, minute = divmod(minute, 60)
    day, hour = divmod(hour, 24)
    month, day = divmod(day, 30)
    year, month = divmod(month, 12)
    if year > 0:
        time = "%02d年%02d月%02d天%02d时%02d分%02d秒" % (year, month, day, hour, minute, sec)
    elif month > 0:
        time = "%02d月%02d天%02d时%02d分%02d秒" % (month, day, hour, minute, sec)
    elif day > 0:
        time = "%02d天%02d时%02d分%02d秒" % (day, hour, minute, sec)
    elif hour > 0:
        time = "%02d时%02d分%02d秒" % (hour, minute, sec)
    elif minute > 0:
        time = "%02d分%02d秒" % (minute, sec)
    else:
        time = f"{sec}秒"
    return time


def mention_user(user):
    if user.username:
        mention = user.username
    else:
        mention = user.id
    return f'`{user.first_name}` [`{mention}`]'


@listener(is_plugin=False, outgoing=True, command=alias_command("fuckadmin"),
          description='列出群组中所有潜水超过 n 天的管理员。（n>=7）。',
          parameters="<day>")
async def fuck_admin(context):
    if context.is_group:
        pass
    else:
        await context.edit('请在群组中运行。')
        return
    await context.edit('遍历管理员中。')
    # 读取天数
    text = ''
    if len(context.parameter) == 1:
        try:
            day = int(context.parameter[0])
            if day < 7:
                day = 7
                text += '由于输入的数据过小，时间自动设置为 7 天。\n'
        except KeyError:
            day = 7
            text += '由于输入的数据错误，时间自动设置为 7 天。\n'
    else:
        day = 7
        text += '由于未输入数据，时间自动设置为 7 天。\n'
    text += f'查找潜水超过 {day} 天的管理员中。'
    await context.edit(text)
    # 获取管理员
    text = f'以下是潜水超过 {day} 天的管理员列表：\n\n'
    msg = 0
    async for x in context.client.iter_participants(context.chat, filter=ChannelParticipantsAdmins):
        async for message in context.client.iter_messages(context.chat_id, limit=1, from_user=x):
            msg += 1
            time = eval_time(context, message, day)
            if time:
                text += f'{mention_user(x)} {time}\n'
            break
        if msg == 1:
            msg = 0
        else:
            text += f'{mention_user(x)} 从未发言\n'
    await context.edit(text)
