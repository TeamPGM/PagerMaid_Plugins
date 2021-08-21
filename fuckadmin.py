from pagermaid.listener import listener
from pagermaid.utils import alias_command
from telethon.tl.types import ChannelParticipantsAdmins


def eval_time(context, msg, day):
    now = context.date
    old = msg.date
    sec = (now - old).seconds
    days = (now - old).days
    if days < day:
        return None
    minute, sec = divmod(sec, 60)
    hour, minute = divmod(minute, 60)

    month, days = divmod(days, 30)
    year, month = divmod(month, 12)
    if year > 0:
        time = "%02d年%02d月%02d天%02d时%02d分%02d秒" % (year, month, days, hour, minute, sec)
    elif month > 0:
        time = "%02d月%02d天%02d时%02d分%02d秒" % (month, days, hour, minute, sec)
    elif day > 0:
        time = "%02d天%02d时%02d分%02d秒" % (days, hour, minute, sec)
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
    admins = 0
    if context.is_group:
        pass
    else:
        await context.edit('请在群组中运行。')
        return
    # 读取天数
    text = ''
    if len(context.parameter) == 1:
        try:
            day = int(context.parameter[0])
            if day < 7:
                day = 7
                text += '由于输入的数据过小，时间自动设置为 7 天。\n'
        except (KeyError or ValueError):
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
                admins += 1
                text += f'{mention_user(x)} {time}\n'
            break
        if msg == 1:
            msg = 0
        else:
            admins += 1
            text += f'{mention_user(x)} 从未发言\n'
    if admins > 0:
        await context.edit(text)
    else:
        await context.edit('没有发现潜水超过 n 天的管理员呢，大家都很活跃！')
