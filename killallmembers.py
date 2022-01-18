""" PagerMaid Plugin killallmembers """
from asyncio import sleep
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors.rpcerrorlist import FloodWaitError
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("killallmembers"),
          description="⚠⚠慎用! 一件扬了群内所有成员⚠⚠")
async def killallmembers(context):
    """ PagerMaid Plugin killallmembers """
    await context.edit('正在准备扬了这个破群的所有人...')
    chat = await context.get_chat()
    is_channel = False
    if not context.is_group:
        if context.is_channel:
            is_channel = True
        else:
            is_channel = False
            await context.edit('发生错误,请在群组或频道中运行本命令。')
            await sleep(10)
            await context.delete()
            return
    try:
        chat = await context.get_chat()
        admins = await context.client.get_participants(chat, filter=ChannelParticipantsAdmins)
        users = await context.client.get_participants(chat)
        admins_ids = [a.id for a in admins]
        users_ids = [u.id for u in users]
        users_wo_admins = list(set(users_ids).difference(set(admins_ids)))
    except:
        await context.edit('发生错误,无法获取本群名单。')
        await sleep(10)
        await context.delete()
        return False

    if (not is_channel) and (context.sender_id not in admins_ids):
        await context.edit('你又不是管理员,你在这儿干个屁?')
        await sleep(10)
        await context.delete()
    else:
        i = 0
        for user_id in users_wo_admins:
            try:
                await context.client.edit_permissions(context.chat_id, user_id, view_messages=False)
                i += 1
                if i == len(users_wo_admins):
                    await context.edit(f'完成！\n进度: {i}/{len(users_wo_admins)}')
                    a = 1
                elif (i < 3) or (i % 10 == 0):
                    percent = i/len(users_wo_admins) * 100
                    await context.edit(f'进度: {i}/{len(users_wo_admins)}\nPercent: {percent:.2f}%')
                await sleep(.5)
            except FloodWaitError as e:
                await context.edit('尝试次数过多,请稍后重试\n' + str(e))
                await sleep(10)
                await context.delete()
                return
            except:
                await context.edit('发生错误')
                await sleep(10)
                await context.delete()
                return
