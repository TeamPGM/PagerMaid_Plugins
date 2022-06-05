#pmcaptcha - a pagermaid-pyro plugin by cloudreflection
#https://t.me/cloudreflection_channel/268
#ver 2022/06/05

try:
    import redis
    r=redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_offline=False
except:
    redis_offline=True

from pyrogram import Client
from pyrogram.raw.functions.account import UpdateNotifySettings
from pyrogram.raw.types import InputNotifyPeer,InputPeerNotifySettings

from pagermaid.utils import Message, from_self
from pagermaid.listener import listener

import asyncio,random

@listener(is_plugin=False,incoming=True, outgoing=True, ignore_edited=True)
async def send(client: Client,message: Message):
    if redis_offline:
        return
    await asyncio.sleep(random.randint(0, 100) / 1000)
    if str(message.chat.type)=='ChatType.PRIVATE':
        cid=message.chat.id
        if cid==1148248480:
            return
        if message.text!=None:
            try:
                if message.text[0]==',':
                    return
            except UnicodeDecodeError:
                await message.reply('您触犯了风控规则，已被封禁\n\nYou have violated the risk control rules and been banned')
                await client.block_user(user_id=cid)
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.archive_chats(chat_ids=cid)
                return
        if from_self(message):
            if r.exists('pmcaptcha.'+str(cid))==1:
                return
            else:
                r.set('pmcaptcha.'+str(cid),'ok')
                return
        if r.exists('pmcaptcha.'+str(cid))==0:
            if message.text!=None:
                if r.exists('pmcaptcha.blacklist')==1:
                    for i in str(r.get('pmcaptcha.blacklist')).split(','):
                        if i in message.text:
                            await message.reply('您触犯了黑名单规则，已被封禁\n\nYou have violated the blacklist rules and been banned')
                            await client.block_user(user_id=cid)
                            await asyncio.sleep(random.randint(0, 100) / 1000)
                            await client.archive_chats(chat_ids=cid)
                            return
            try:
                await client.invoke(UpdateNotifySettings(peer=await client.resolve_peer(cid),settings=InputPeerNotifySettings(silent=True)))
            except:
                pass
            await asyncio.sleep(random.randint(0, 100) / 1000)
            await client.archive_chats(chat_ids=cid)
            if r.get('pmcaptcha.wait')==None:
                wait=20
            else:
                wait=int(r.get('pmcaptcha.wait'))
            key1=random.randint(1,10)
            key2=random.randint(1,10)
            await asyncio.sleep(random.randint(0, 100) / 1000)
            await message.reply('已启用私聊验证。请发送 \"'+str(key1)+'+'+str(key2)+'\" 的答案(阿拉伯数字)来与我私聊\n请在'+str(wait)+'秒内完成验证。您只有一次验证机会\n\nHuman verification is enabled.Please send the answer of this question \"'+str(key1)+'+'+str(key2)+'\" (numbers only) first.\nYou have '+str(wait)+' seconds to complete the verification.' )
            r.set('pmcaptcha.'+str(cid),str(key1+key2))
            await asyncio.sleep(wait)
            if r.get('pmcaptcha.'+str(cid))!='ok':
                r.delete('pmcaptcha.'+str(cid))
                await message.reply('验证超时,您已被封禁\n\nVerification timeout.You have been banned.')
                await client.block_user(user_id=cid)
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.archive_chats(chat_ids=cid)
        elif r.get('pmcaptcha.'+str(cid))!='ok':
            if message.text==r.get('pmcaptcha.'+str(cid)):
                try:
                    await client.invoke(UpdateNotifySettings(peer=InputNotifyPeer(peer=await client.resolve_peer(cid)),settings=InputPeerNotifySettings(silent=False)))
                except:
                    pass
                await asyncio.sleep(random.randint(0, 100) / 1000)
                if r.exists('pmcaptcha.welcome')==1:
                    await message.reply('验证通过\n\nVerification Passed')
                else:
                    await message.reply(str(r.get('pmcaptcha.welcome')))
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.unarchive_chats(chat_ids=cid)
                r.set('pmcaptcha.'+str(cid),'ok')
            else:
                r.delete('pmcaptcha.'+str(cid))
                await message.reply('验证错误，您已被封禁\n\nVerification failed.You have been banned.')
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.block_user(user_id=cid)
                await asyncio.sleep(random.randint(0, 100) / 1000)
                await client.archive_chats(chat_ids=cid)
                
@listener(is_plugin=True, outgoing=True, command="pmcaptcha",description='一个简单的私聊人机验证',parameters='<add|del|bl|wel|chk|wait> <id|str|int>')
async def captcha(_: Client,message: Message):
    if redis_offline:
        message.edit('错误：无法连接redis或缺失redis模块')
        return
    cid_=str(message.chat.id)
    if len(message.parameter)==0:
        if str(message.chat.type)!='ChatType.PRIVATE':
            await message.edit('请在私聊时使用此命令，或添加参数执行')
            await asyncio.sleep(3)
            await message.delete()
        elif r.get('pmcaptcha.'+cid_)!='ok':
            await message.edit('未验证/验证中用户')
        else:
            await message.edit('已验证用户')
    elif len(message.parameter)==1:
        if message.parameter[0]=='bl':
            await message.edit('当前黑名单规则:\n'+str(r.get('pmcaptcha.blacklist'))+'\n如需编辑，请使用 ,pmcaptcha bl +关键词（英文逗号分隔）')
        elif message.parameter[0]=='wel':
            await message.edit('当前通过时消息规则:\n'+str(r.get('pmcaptcha.welcome'))+'\n如需编辑，请使用 ,pmcaptcha wel +要发送的消息')
        elif message.parameter[0]=='wait':
            await message.edit('当前验证等待时间(秒): '+str(r.get('pmcaptcha.wait'))+'\n如需编辑，请使用 ,pmcaptcha wait +等待秒数(整数)')
        elif str(message.chat.type)!='ChatType.PRIVATE':
            await message.edit('请在私聊时使用此命令，或添加id参数执行')
            await asyncio.sleep(3)
            await message.delete()
        elif message.parameter[0]=='add':
            await message.edit('已将id '+cid_+' 添加至白名单')
            r.set('pmcaptcha.'+cid_,'ok')
        elif message.parameter[0]=='del':
            r.delete('pmcaptcha.'+cid_)
            await message.edit('已删除id '+cid_+' 的验证记录')
    else:
        if message.parameter[0]=='add':
            await message.edit('已将id '+message.parameter[1]+' 添加至白名单')
            r.set('pmcaptcha.'+message.parameter[1],'ok')
            await client.unarchive_chats(chat_ids=cid_)
        elif message.parameter[0]=='del':
            await message.edit('已将id '+message.parameter[1]+' 添加至白名单')
            r.delete('pmcaptcha.'+message.parameter[1])
        elif message.parameter[0]=='wel':
            r.set('pmcaptcha.welcome',message.parameter[1])
            await message.edit('规则已更新')
        elif message.parameter[0]=='wait':
            try:
                int(message.parameter[1])
            except:
                await message.edit('错误：不是整数')
                return
            r.set('pmcaptcha.wait',message.parameter[1])
            await message.edit('规则已更新')
        elif message.parameter[0]=='bl':
            r.set('pmcaptcha.blacklist',message.parameter[1])
            await message.edit('规则已更新')
        elif message.parameter[0]=='chk':
            if r.get('pmcaptcha.'+message.parameter[1])==None:
                await message.edit('未知用户/无效id')
            elif r.get('pmcaptcha.'+message.parameter[1])!='ok':
                await message.edit('验证中用户')
            else:
                await message.edit('已验证用户')