import json

from pagermaid import bot, version, persistent_vars
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid.utils import client

"""
Pagermaid sillyGirl plugin.

Silly Gril Repo: https://github.com/cdle/sillyGirl
"""


async def poll(data):
    try:
        req_data = await client.post(f"http://127.0.0.1:8080/pgm", json=data)
    except Exception:  # noqa
        print('出错了呜呜呜 ~ 无法访问 API ')
        return

    if not req_data or req_data.status_code != 200:
        print('出错了呜呜呜 ~ 无法访问 API ')
        return

    try:
        for reply in json.loads(req_data.text):
            text = reply["text"]
            images = reply["images"]
            chat_id = reply["chat_id"]
            reply_to = reply["reply_to"]

            if images and len(images) != 0:
                await bot.send_file(
                    chat_id,
                    images[0],
                    caption=text,
                    reply_to=reply_to,
                )
            elif text != '':
                await bot.send_message(chat_id, text, reply_to=reply_to)

    except Exception:  # noqa
        print("出错了呜呜呜 ~ 解析JSON时发生了错误。")


@listener(is_plugin=True, outgoing=True, command=alias_command("sillyGirl"), diagnostics=True, ignore_edited=True)
async def silly_girl_wrap(context):
    if not persistent_vars["sillyGirl"]['started']:
        myself = await context.client.get_me()
        persistent_vars["sillyGirl"]['self_user_id'] = myself.id
        persistent_vars["sillyGirl"]['started'] = True
        await context.edit("已对接傻妞。")
        while True:
            await poll({})
    else:
        await context.delete()


@listener(is_plugin=True, outgoing=True, incoming=True)
async def private_respond(context):
    reply_to = context.id
    reply_to_sender_id = 0
    reply = await context.get_reply_message()

    if reply:
        reply_to = reply.id
        reply_to_sender_id = reply.sender_id
    elif persistent_vars["sillyGirl"]['self_user_id'] == context.sender_id or context.is_private:
        reply_to = 0

    await poll({
        'id': context.id,
        'chat_id': context.chat_id,
        'text': context.text,
        'sender_id': context.sender_id,
        'reply_to': reply_to,
        'reply_to_sender_id': reply_to_sender_id,
    })


persistent_vars.update({'sillyGirl': {'times': 0, 'started': False, 'self_user_id': 0}})
