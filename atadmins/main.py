from telethon.tl.types import ChannelParticipantsAdmins

from pagermaid.listener import listener
from pagermaid.enums import Message


@listener(
    command="atadmins",
    description="一键 AT 本群管理员（仅在群组中有效）",
    parameters="回复消息(可选) <要说的话(可选)>",
)
async def atadmins(context: "Message"):
    await context.edit('正在获取管理员列表中...')
    chat = await context.get_chat()
    try:
        admins = await context.client.get_participants(chat, filter=ChannelParticipantsAdmins)
    except:
        await context.edit('请在群组中运行。')
        return True
    admin_list = []
    if context.arguments == '':
        say = '召唤本群所有管理员'
    else:
        say = context.arguments
    for admin in admins:
        if not admin.bot:
            if admin.username is not None:
                admin_list.extend(['@' + admin.username])
            elif admin.first_name is not None:
                admin_list.extend(['[' + admin.first_name + '](tg://user?id=' + str(admin.id) + ')'])
    send_list = ' , '.join(admin_list)
    reply = await context.get_reply_message()
    if reply:
        await reply.reply(f'{say}:\n{send_list}')
    else:
        await context.reply(f'{say}:\n{send_list}')
    await context.delete()
