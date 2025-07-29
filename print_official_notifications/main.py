from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils import logs


@listener(incoming=True, outgoing=True, privates_only=True)
async def print_official_notifications(message: Message):
    if message.sender_id not in [777000]:
        return
    logs.info(
        f"Official notification from {message.from_user.first_name}: {message.text}"
    )
