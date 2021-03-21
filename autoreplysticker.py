""" Pagermaid Plugins AutoReplySticker """
#   ______          _
#   | ___ \        | |
#   | |_/ /__ _ __ | |_ __ _  ___ ___ _ __   ___
#   |  __/ _ \ '_ \| __/ _` |/ __/ _ \ '_ \ / _ \
#   | | |  __/ | | | || (_| | (_|  __/ | | |  __/
#   \_|  \___|_| |_|\__\__,_|\___\___|_| |_|\___|
#

from os import mkdir
from os.path import exists
from asyncio import sleep
from random import randint
import yaml
from telethon.tl.functions.messages import GetAllStickersRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetID
from pagermaid import log
from pagermaid.listener import listener

async def ars_check(context):
    try:
        config = yaml.load(open(r"./plugins/autoreplysticker/config.yml"), Loader=yaml.FullLoader)
    except FileNotFoundError:
        await context.edit("自动回复贴纸的相关设置不存在。\n请使用 `-ars help` 查看设置方法")
        return
    _sticker_id = config['sticker_id']
    _sticker_hash = config['sticker_hash']
    _num = config['num']
    _time = config['time']
    _noti = await context.reply(
        '您当前的设置为:\n'
        f'sticker_id: {_sticker_id}\n'
        f'sticker_hash: {_sticker_hash}\n'
        f'time: {_time}\n'
        f'num: {_num}')
    await context.delete()
    await sleep(15)
    await _noti.delete()

async def ars_getall(context):
    sticker_sets = await context.client(GetAllStickersRequest(0))
    sticker_pack_list = []
    for sticker_set in sticker_sets.sets:
        if len(sticker_pack_list) < 10:
            text = "我发现了一个Sticker Pack，名为\n" + sticker_set.title + "\n" + "ID为： `" + \
                str(sticker_set.id) + "` \n" + "Hash为： `" + str(sticker_set.access_hash) + \
                "` \n" + "共有" + str(sticker_set.count) + "张"
            sticker_pack_list.extend([text])
        else:
            sticker_pack_list_old = sticker_pack_list
            send_text = '\n\n'.join(sticker_pack_list_old)
            await context.client.send_message(context.chat_id, send_text)
            sticker_pack_list = []
            await sleep(2)
    sendtext = '\n\n'.join(sticker_pack_list)
    await context.client.send_message(context.chat_id, sendtext)
    await context.delete()

async def ars_help(context):
    await context.reply(
        '欢迎使用自动回复贴纸\n'
        '设置方法为\n'
        '先使用 `-ars getall` 获取贴纸包的id和hash\n'
        '之后使用 `-ars set` 贴纸包id 贴纸包hash 自动删除时间 第i张贴纸 第j张贴纸 ...\n'
        '比如 `-ars set 000 001 10 0 1 2 3` 的意义为\n'
        '设置贴纸包id为000, hash为001, 自动回复10秒后删除, 随机从第0, 1, 2, 3张贴纸中选择一张自动回复\n\n'
        '如有使用问题,请前往 [这里](https://t.me/PagerMaid_Modify) 请求帮助')
    await context.delete()

def set_state(name, state):
    file_name = "./plugins/autoreplysticker/config.yml"
    if exists(file_name):
        with open(file_name) as f:
            doc = yaml.safe_load(f)
        doc[name] = state
        with open(file_name, 'w') as f:
            yaml.safe_dump(doc, f, default_flow_style=False)
    else:
        dc = {name: state}
        with open(file_name, 'w', encoding='utf-8') as f:
            yaml.dump(dc, f)

def get_name(sender):
    """
    get_name(Message.sender)
    """
    username = sender.username 
    first_name = sender.first_name
    last_name = sender.last_name
    _id = sender.id
    if username == None:
        if last_name == None:
            name = f'[{first_name}](tg://user?id={_id})'
        else:
            name = f'[{first_name}{last_name}](tg://user?id={_id})'
    else:
        name = f'@{username}'
    return name

def process_link(chatid, msgid):
    """
    process_link(chat_id, message_id)
    return https://t.me/c/chat_id/message_id
    """
    if chatid < 0:
        if chatid < -1000000000000:
            chatid *= -1
            chatid -= 1000000000000
        else:
            chatid *= -1
    link = f'https://t.me/c/{chatid}/{msgid}'
    return link

@listener(is_plugin=True, outgoing=True, command="ars")
async def ars(context):
    if not exists('./plugins/autoreplysticker'):
        mkdir('./plugins/autoreplysticker')

    if context.parameter[0] == 'set':
        if len(context.parameter) < 5:
            await context.reply('请正确输入 `-ars set` <sticker_id> <sticker_hash> <time> <num>')
            await context.delete()
            return
        try:
            set_state('sticker_id', context.parameter[1])
            set_state('sticker_hash', context.parameter[2])
            set_state('time', context.parameter[3])
            num_list = []
            for i in range(4, len(context.parameter)):
                num_list.append(context.parameter[i])
            set_state('num', num_list)
        except:
            await context.reply('设置失败,请手动设置`./plugins/autoreplysticker/config.yml`')
            return
        _noti = await context.reply('设置成功')
        await sleep(10)
        await _noti.delete()
        await ars_check(context)
    
    elif context.parameter[0] == 'check':
        await ars_check(context)
    elif context.parameter[0] == 'getall':
        await ars_getall(context)
    elif context.parameter[0] == 'help':
        await ars_help(context)

@listener(incoming=True)
async def process_message(context):
    reply_user_id = 0
    link = process_link(context.chat_id, context.id)
    me = await context.client.get_me()
    try:
        reply = await context.get_reply_message()
        reply_user_id = reply.sender.id
        if context.sticker:
            return
    except:
        pass
    
    try:
        config = yaml.load(open(r"./plugins/autoreplysticker/config.yml"), Loader=yaml.FullLoader)
        _sticker_id = int(config['sticker_id'])
        _sticker_hash = int(config['sticker_hash'])
        _num = config['num']
        _time = int(config['time'])
    except:
        return

    if (reply and reply_user_id == me.id):
        stickers = await context.client(
            GetStickerSetRequest(
                stickerset=InputStickerSetID(
                    id=_sticker_id, access_hash=_sticker_hash)))
        try:
            i = randint(0, len(_num)-1)
            sticker = await context.client.send_file(
                context.chat_id,
                stickers.documents[int(_num[i])],
                reply_to=context.id)
            await sleep(_time)
            await sticker.delete()
            if context.chat_id < 0:
                await log(
                    f'#被回复\n在 [{context.chat.title}]({process_link(context.chat_id, context.id)})\n'
                    f'获得了 {get_name(context.sender)} 的回复')
        except:
            pass
