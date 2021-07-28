""" Module to automate sticker deletion. """
from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import alias_command, lang


@listener(is_plugin=True, outgoing=True, command=alias_command("fuckmessage"),
          description="删除最近 200 条消息中包含指定关键字的消息。",
          parameters="<关键词>")
async def fuck_message(context):
    """ Deletes specific amount of messages in chat. """
    if not context.arguments:
        await context.edit(lang('arg_error'))
        return
    input_chat = await context.get_input_chat()
    count_buffer = 0
    count = 0
    messages = []
    async for message in context.client.iter_messages(context.chat_id):
        if count_buffer == 200:
            break
        if message.text:
            if context.arguments in message.text:
                messages.append(message)
                count += 1
        if len(messages) > 50:
            try:
                await context.client.delete_messages(input_chat, messages)
            except Exception as e:
                await log(f'插件 fuckmessage 发生错误：\n{e}')
        count_buffer += 1
    text = f"删除了 {count} / {count_buffer} 条 消息 。"
    try:
        await context.client.delete_messages(input_chat, messages)
    except Exception as e:
        await log(f'插件 fuckmessage 发生错误：\n{e}')
    await log(text)
