import contextlib

from pagermaid.dependence import add_delete_message_job
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid.utils.bot_utils import log


@listener(
    command="da",
    groups_only=True,
    need_admin=True,
    description="删除群内所有消息。（非群组管理员只删除自己的消息）",
    parameters="[true]",
)
async def da(message: Message):
    if message.arguments != "true":
        return await message.edit(
            f"[da] 呜呜呜，请执行 `,{alias_command('da')} true` 来删除所有消息。"
        )
    await message.edit("[da] 正在删除所有消息 . . .")
    input_chat = await message.get_input_chat()
    messages = []
    count = 0
    async for message in message.client.iter_messages(input_chat, min_id=1):
        messages.append(message)
        count += 1
        if count % 100 == 0:
            with contextlib.suppress(Exception):
                await message.client.delete_messages(input_chat, messages)
            messages = []

    if messages:
        with contextlib.suppress(Exception):
            await message.client.delete_messages(input_chat, messages)
    await log(f"批量删除了 {str(count)} 条消息。")
    with contextlib.suppress(Exception):
        reply = await message.client.send_message(
            message.chat_id, "批量删除了 " + str(count) + " 条消息。"
        )
        add_delete_message_job(reply, delete_seconds=5)
