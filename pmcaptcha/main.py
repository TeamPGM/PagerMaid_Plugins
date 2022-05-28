try:
    import redis
except:
    exit(0)

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateNotifySettings
from pyrogram.raw.types import InputNotifyPeer,InputPeerNotifySettings

from pagermaid.utils import Message, from_self
from pagermaid.listener import listener

import asyncio,random

r=redis.Redis(host='localhost', port=6379, decode_responses=True)

@listener(is_plugin=False,incoming=True, outgoing=True, ignore_edited=True)
async def send(client: Client,message: Message):
    await asyncio.sleep(random.randint(0, 100) / 1000)
    if str(message.chat.type)=='ChatType.PRIVATE':
        cid=message.chat.id
        if from_self(message):
            if r.exists('pmcaptcha.'+str(cid))==1:
                return
            else:
                r.set('pmcaptcha.'+str(cid),'ok')
                return
        if r.exists('pmcaptcha.'+str(cid))==0:
            for i in str(r.get('pmcaptcha.blacklist')).split(','):
                if i in message.text:
                    await message.reply('您触犯了黑名单规则，已被封禁')
                    await asyncio.sleep(random.randint(0, 100) / 1000)
                    await client.archive_chats(chat_ids=cid)
                    await asyncio.sleep(random.randint(0, 100) / 1000)
                    await client.block_user(user_id=cid)
                    return
            try:
                await client.invoke(UpdateNotifySettings(peer=client.resolve_peer(cid),settings=InputPeerNotifySettings(silent=True)))
            except:
                pass
            #AttributeError: 'coroutine' object has no attribute 'write'
            await asyncio.sleep(random.randint(0, 100) / 1000)
            await client.archive_chats(chat_ids=cid)
            key1=random.randint(1,10)
            key2=random.randint(1,10)
            await asyncio.sleep(random.randint(0, 100) / 1000)
            await message.reply('已启用私聊验证。请发送 \"'+str(key1)+'+'+str(key2)+'\" 的答案(阿拉伯数字)来与我私聊\n请注意，您只有一次验证机会\n\nCaptcha is enabled.Please send the answer of this question \"'+str(key1)+'+'+str(key2)+'\" (numbers only) first.' )
            r.set('pmcaptcha.'+str(cid),str(key1+key2))
        elif r.get('pmcaptcha.'+str(cid))!='ok':
            if message.text==r.get('pmcaptcha.'+str(cid)):
                try:
                    await client.invoke(UpdateNotifySettings(peer=InputNotifyPeer(peer=client.resolve_peer(cid)),settings=InputPeerNotifySettings(silent=False)))
                except:
                    pass
                await asyncio.sleep(random.randint(0, 100) / 1000)
                if r.get('pmcaptcha.welcome')==None:
                    await message.reply('验证通过')
                else:
                    await message.reply(str(r.get('pmcaptcha.welcome')))
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.unarchive_chats(chat_ids=cid)
                r.set('pmcaptcha.'+str(cid),'ok')
            else:
                r.delete('pmcaptcha.'+str(cid))
                await message.reply('验证错误，您已被封禁')
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.block_user(user_id=cid)
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.archive_chats(chat_ids=cid)
                
@listener(is_plugin=True, outgoing=True, command="pmcaptcha",description='一个简单的私聊人机验证 支持自定义验证成功后消息及关键词黑名单 需要redis',parameters='<add|del|bl|wel|chk> <id|str>')
async def captcha(_: Client,message: Message):
    cid_=str(message.chat.id)
    if len(message.parameter)==0:
        if str(message.chat.type)!='ChatType.PRIVATE':
            await message.edit('请在私聊时使用此命令，或添加参数执行')
            await asyncio.sleep(3)
            await message.delete()
            return
        if r.get('pmcaptcha.'+cid_)!='ok':
            await message.edit('未验证/验证中用户')
            return
        else:
            await message.edit('已验证用户')
            return
    if len(message.parameter)==1:
        if message.parameter[0]=='bl':
            await message.edit('当前黑名单规则:\n'+str(r.get('pmcaptcha.blacklist'))+'\n如需编辑，请使用 ,pmcaptcha bl +关键词（英文逗号分隔）')
            return
        if message.parameter[0]=='wel':
            await message.edit('当前通过时消息规则:\n'+str(r.get('pmcaptcha.welcome'))+'\n如需编辑，请使用 ,pmcaptcha wel +要发送的消息')
            return
        if str(message.chat.type)!='ChatType.PRIVATE':
            await message.edit('请在私聊时使用此命令，或添加id参数执行')
            await asyncio.sleep(3)
            await message.delete()
            return
        if message.parameter[0]=='add':
            await message.edit('已将id '+cid_+' 添加至白名单')
            r.set('pmcaptcha.'+cid_,'ok')
            return
        elif message.parameter[0]=='del':
            r.delete('pmcaptcha.'+cid_)
            await message.edit('已删除id '+cid_+' 的验证记录')
            return
    else:
        if message.parameter[0]=='add':
            await message.edit('已将id '+message.parameter[1]+' 添加至白名单')
            r.set('pmcaptcha.'+message.parameter[1],'ok')
            return
        elif message.parameter[0]=='del':
            await message.edit('已将id '+message.parameter[1]+' 添加至白名单')
            r.delete('pmcaptcha.'+message.parameter[1])
            return
        elif message.parameter[0]=='wel':
            r.set('pmcaptcha.welcome',message.parameter[1])
            await message.edit('规则已更新')
            return
        elif message.parameter[0]=='bl':
            r.set('pmcaptcha.blacklist',message.parameter[1])
            await message.edit('规则已更新')
        elif message.parameter[0]=='chk':
            if r.get('pmcaptcha.'+message.parameter[1])==None:
                await message.edit('未知用户/无效id')
                return
            elif r.get('pmcaptcha.'+message.parameter[1])!='ok':
                await message.edit('验证中用户')
                return
            else:
                await message.edit('已验证用户')