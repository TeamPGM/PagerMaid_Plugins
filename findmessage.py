""" Module to automate sticker deletion. """
from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import alias_command, lang


@listener(is_plugin=True, outgoing=True, command=alias_command("findmessage"),
          description="查找最近 xx 条消息中包含指定关键字的消息，并推送相应链接人名及信息至Log频道。",
          parameters="<关键词>")
async def fuck_message(context):
    """Find specific amount of messages in chat. """
    if not context.arguments:
        await context.edit(lang('arg_error'))
        return
    input_chat = await context.get_input_chat()
    count_buffer = 0
    count = 0
    messages = ""
    chatid = context.chat_id
    await context.edit('正在搜索中')
    if chatid < 0:
        if chatid < -1000000000000:
            chatid *= -1
            chatid -= 1000000000000
        else:
            chatid *= -1
    async for message in context.client.iter_messages(context.chat_id):
        if count_buffer == 50:
            break
        if message.text:
            if context.arguments[0] in message.text:
                link = f"https://t.me/c/{chatid}/{message.id}"
                messages += f"\n[{message.sender.first_name}]({link})" + ":" + message.text 
        count_buffer += 1
    text = f"搜索了 {count_buffer} 条 消息\n结果如下:\n{messages}"
    await context.delete()
    await log(
                f'{text}')
