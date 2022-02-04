from pagermaid.listener import listener
from pagermaid import persistent_vars, bot
from pagermaid.utils import client, alias_command
import os
import json

"""
Pagermaid sillyGirl plugin.
Silly Gril Repo: https://github.com/cdle/sillyGirl
"""

persistent_vars.update(
    {'sillyGirl':
        {
            'times': 0,
            'started': False,
            'self_user_id': 0,
            'secret': '',
            'url': '',
            'init': False,
            'whiltelist': '',
        }
     }
)

@listener(is_plugin=True, outgoing=True, command=alias_command("sillyGirl"), ignore_edited=True, parameters="<message>")
async def sillyGirl(context):
    fd = os.open("sillyGirl.egg", os.O_RDWR | os.O_CREAT)
    await context.edit("正在连接到傻妞服务器...")
    persistent_vars["sillyGirl"]['context'] = context
    persistent_vars["sillyGirl"]['init'] = False
    if context.arguments:
        text = context.arguments
        try:
            os.write(fd, bytes(text, 'utf-8'))
        except Exception as e:
            print(e)
    else:
        try:
            text = str(os.read(fd, 1200), encoding="utf-8")
        except Exception as e:
            print(e)
    if '@' in text:
        s1 = text.split("//", 1)
        s2 = s1[1].split("@", 1)
        persistent_vars["sillyGirl"]['secret'] = s2[0]
        text = s1[0]+"//"+s2[1]
    os.close(fd)
    persistent_vars["sillyGirl"]['url'] = text
    myself = await context.client.get_me()
    persistent_vars["sillyGirl"]['self_user_id'] = myself.id
    if persistent_vars["sillyGirl"]['started'] == False:
        persistent_vars["sillyGirl"]['started'] = True
        while(True):
            await poll([])


@listener(is_plugin=True, outgoing=True, incoming=True)
async def xxx(context):
    if persistent_vars["sillyGirl"]['started'] == False:
        return
    reply_to = 0
    reply_to = context.id
    reply = await context.get_reply_message()
    reply_to_sender_id = 0
    if context.sender_id == persistent_vars["sillyGirl"]['self_user_id'] or str(context.sender_id) in persistent_vars["sillyGirl"]['whiltelist'] or str(context.chat_id) in persistent_vars["sillyGirl"]['whiltelist']:
        if reply:
            reply_to = reply.id
            reply_to_sender_id = reply.sender_id
        elif persistent_vars["sillyGirl"]['self_user_id'] == context.sender_id or context.is_private:
            reply_to = 0
        await poll(
            [{
                'id': context.id,
                'chat_id': context.chat_id,
                'text': context.text,
                'sender_id': context.sender_id,
                'reply_to': reply_to,
                'reply_to_sender_id': reply_to_sender_id,
                'bot_id': persistent_vars["sillyGirl"]['self_user_id'],
                'is_group': context.is_private == False,
            }])


async def poll(data):
    try:
        init = ""
        if persistent_vars["sillyGirl"]['init'] == False:
            init = "?init=true"
        req_data = await client.post(persistent_vars["sillyGirl"]['url']+"/pgm"+init, json=data)
    except Exception as e:
        return
    if not req_data.status_code == 200:
        return
    try:
        replies = json.loads(req_data.text)
        results = []
        for reply in replies:
            if reply["whiltelist"] != "":
                persistent_vars["sillyGirl"]['whiltelist'] = reply["whiltelist"]
                await persistent_vars["sillyGirl"]['context'].edit("获取白名单中...")
                continue
            if reply["delete"]:
                try:
                    await bot.edit_message(reply["chat_id"], reply["id"], "打错字了，呱呱～")
                except Exception as e:
                    """"""
                try:
                    await bot.delete_messages(reply["chat_id"], [reply["id"]])
                except Exception as e:
                    """"""
            if reply["id"] != 0:
                try:
                    await bot.edit_message(reply["chat_id"], reply["id"], reply["text"])
                    continue
                except Exception as e:
                    continue
                
            text = reply["text"]
            images = reply["images"]
            chat_id = reply["chat_id"]
            reply_to = reply["reply_to"]
            context = False
            if images and len(images) != 0:
                context = await bot.send_file(
                    chat_id,
                    images[0],
                    caption=text,
                    reply_to=reply_to,
                )
            elif text != '':
                context = await bot.send_message(chat_id, text, reply_to=reply_to)
            if context:
                results.append({
                    'id': context.id,
                    'uuid': reply["uuid"],
                })
        if len(results):
            await poll(results)
        if persistent_vars["sillyGirl"]['init'] == False:
            persistent_vars["sillyGirl"]['init'] = True
            await persistent_vars["sillyGirl"]['context'].edit("傻妞连接成功，愉快玩耍吧。")
            await persistent_vars["sillyGirl"]['context'].delete()
    except Exception as e:
        return
