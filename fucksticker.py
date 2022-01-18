""" Module to automate sticker deletion. """
from asyncio import sleep
from pagermaid import log, version
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("fucksticker"),
          description="删除最近 50 条消息中的 sticker 。"
                      "无管理员权限将只删除自己发送的 sticker 。")
async def fucksticker(context):
    """ Deletes specific amount of stickers in chat. """
    input_chat = await context.get_input_chat()
    count_buffer = 0
    count = 0
    messages = []
    async for message in context.client.iter_messages(context.chat_id):
        if count_buffer == 50:
            break
        if message.sticker:
            count += 1
            messages.append(message)
        else:
            pass
        count_buffer += 1
    text = f"删除了 {count} / {count_buffer} 条 sticker 。"
    try:
        await context.client.delete_messages(input_chat, messages)
    except Exception as e:
        text = f"删除了 {count_buffer} 条消息中的 sticker 。"
        await log(f'插件 fucksticker 发生错误：\n{e}')
    await context.edit(text)
    await sleep(1)
    await context.delete()
