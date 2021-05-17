""" Pagermaid plugin delete messages from groups """
#   ______          _
#   | ___ \        | |
#   | |_/ /__ _ __ | |_ __ _  ___ ___ _ __   ___
#   |  __/ _ \ '_ \| __/ _` |/ __/ _ \ '_ \ / _ \
#   | | |  __/ | | | || (_| | (_|  __/ | | |  __/
#   \_|  \___|_| |_|\__\__,_|\___\___|_| |_|\___|
#

from asyncio import sleep
from telethon.tl.custom.message import Message
from pagermaid.listener import listener

@listener(is_plugin=True, outgoing=True, command="dmfg")
async def dmfg(context: Message) -> None:
    if len(context.parameter) == 0:
        await context.edit('您没有输入参数.\n`-dmfg group` 删除所有群内发言\n`-dmfg private` 删除所有与人的对话消息')
        return
    if context.parameter[0] == 'group':
        await context.edit('准备中...')
        count = 1000000
        count_buffer = 0
        await context.edit('执行中...')
        async for dialog in context.client.iter_dialogs():
            if dialog.is_channel and not dialog.is_group:
                continue
            if dialog.id > 0:
                continue
            async for message in context.client.iter_messages(dialog.id, from_user="me"):
                if count_buffer == count:
                    break
                await message.delete()
                count_buffer += 1
        await context.edit('成功!')
        await sleep(5)
        await context.delete()
    elif context.parameter[0] == 'private':
        await context.edit('准备中...')
        count = 1000000
        count_buffer = 0
        await context.edit('执行中...')
        async for dialog in context.client.iter_dialogs():
            if dialog.id > 0:
                async for message in context.client.iter_messages(dialog.id, from_user="me"):
                    if count_buffer == count:
                        break
                    await message.delete() 
                    count_buffer += 1
        await context.edit('成功!')
        await sleep(5)
        await context.delete()
    else:
        await context.edit('您输入的参数错误.\n`-dmfg group` 删除所有群内发言\n`-dmfg private` 删除所有与人的对话消息')
