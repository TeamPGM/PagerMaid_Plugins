""" PagerMaid Plugins Paolu """

import contextlib

from pagermaid.dependence import add_delete_message_job
from pagermaid.listener import listener
from pagermaid.enums import Message


@listener(
    command="paolu", groups_only=True, need_admin=True, description="⚠一键跑路 删除群内消息并禁言⚠"
)
async def pao_lu(message: Message):
    """一键跑路 删除群内消息并禁言"""
    with contextlib.suppress(Exception):
        await message.client.edit_permissions(
            entity=message.chat_id,
            send_messages=False,
            send_media=False,
            send_stickers=False,
            send_gifs=False,
            send_games=False,
            send_inline=False,
            send_polls=False,
            invite_users=False,
            change_info=False,
            pin_messages=False)
    reply = await message.edit("[paolu] 处理中...")
    with contextlib.suppress(Exception):
        await message.client.delete_messages(message.chat_id, list(range(1, message.id)))
    await reply.edit("[paolu] Finished")
    add_delete_message_job(reply, delete_seconds=10)
