""" Pagermaid plugin base. """
import json, requests, re
from urllib.parse import urlparse
from pagermaid import bot, log
from pagermaid.listener import listener, config
from pagermaid.utils import clear_emojis, obtain_message, attach_log, alias_command
from telethon.errors import ChatAdminRequiredError
from telethon.errors.rpcerrorlist import FloodWaitError, UserAdminInvalidError
from telethon.tl.types import ChannelParticipantsAdmins, ChannelParticipantsBots, ChannelParticipantAdmin


@listener(is_plugin=True, outgoing=True, command=alias_command("guess"),
          description="能不能好好说话？ - 拼音首字母缩写释义工具（需要回复一句话）")
async def guess(context):
    reply = await context.get_reply_message()
    await context.edit("获取中 . . .")
    if not reply:
        context.edit("宁需要回复一句话")
        return True
    text = {'text': str(reply.message.replace("/guess ", "").replace(" ", ""))}
    guess_json = json.loads(
        requests.post("https://lab.magiconch.com/api/nbnhhsh/guess", data=text, verify=False).content.decode("utf-8"))
    guess_res = []
    if not len(guess_json) == 0:
        for num in range(0, len(guess_json)):
            guess_res1 = json.loads(json.dumps(guess_json[num]))
            guess_res1_name = guess_res1['name']
            try:
                guess_res1_ans = ", ".join(guess_res1['trans'])
            except:
                try:
                    guess_res1_ans = ", ".join(guess_res1['inputting'])
                except:
                    guess_res1_ans = "尚未录入"
            guess_res.extend(["词组：" + guess_res1_name + "\n释义：" + guess_res1_ans])
        await context.edit("\n\n".join(guess_res))
    else:
        await context.edit("没有匹配到拼音首字母缩写")


@listener(is_plugin=True, outgoing=True, command=alias_command("wiki"),
          description="查询维基百科词条",
          parameters="<词组>")
async def wiki(context):
    await context.edit("获取中 . . .")
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    try:
        wiki_json = json.loads(requests.get("https://zh.wikipedia.org/w/api.php?action=query&list=search&format=json"
                                            "&formatversion=2&srsearch=" + message).content.decode(
            "utf-8"))
    except:
        await context.edit("出错了呜呜呜 ~ 无法访问到维基百科。")
        return
    if not len(wiki_json['query']['search']) == 0:
        wiki_title = wiki_json['query']['search'][0]['title']
        wiki_content = wiki_json['query']['search'][0]['snippet'].replace('<span class=\"searchmatch\">', '**').replace(
            '</span>', '**')
        wiki_time = wiki_json['query']['search'][0]['timestamp'].replace('T', ' ').replace('Z', ' ')
        message = '词条： [' + wiki_title + '](https://zh.wikipedia.org/zh-cn/' + wiki_title + ')\n\n' + \
                    wiki_content + '...\n\n此词条最后修订于 ' + wiki_time
        await context.edit(message)
    else:
        await context.edit("没有匹配到相关词条")


@listener(is_plugin=True, outgoing=True, command=alias_command("ip"),
          description="IPINFO （或者回复一句话）",
          parameters="<ip/域名>")
async def ipinfo(context):
    reply = await context.get_reply_message()
    await context.edit('正在查询中...')
    try:
        if reply:
            for num in range(0, len(reply.entities)):
                url = reply.message[reply.entities[num].offset:reply.entities[num].offset + reply.entities[num].length]
                url = urlparse(url)
                if url.hostname:
                    url = url.hostname
                else:
                    url = url.path
                ipinfo_json = json.loads(requests.get(
                    "http://ip-api.com/json/" + url + "?fields=status,message,country,regionName,city,lat,lon,isp,"
                                                      "org,as,mobile,proxy,hosting,query").content.decode(
                    "utf-8"))
                if ipinfo_json['status'] == 'fail':
                    pass
                elif ipinfo_json['status'] == 'success':
                    ipinfo_list = []
                    ipinfo_list.extend(["查询目标： `" + url + "`"])
                    if ipinfo_json['query'] == url:
                        pass
                    else:
                        ipinfo_list.extend(["解析地址： `" + ipinfo_json['query'] + "`"])
                    ipinfo_list.extend(["地区： `" + ipinfo_json['country'] + ' - ' + ipinfo_json['regionName'] + ' - ' +
                                        ipinfo_json['city'] + "`"])
                    ipinfo_list.extend(["经纬度： `" + str(ipinfo_json['lat']) + ',' + str(ipinfo_json['lon']) + "`"])
                    ipinfo_list.extend(["ISP： `" + ipinfo_json['isp'] + "`"])
                    if not ipinfo_json['org'] == '':
                        ipinfo_list.extend(["组织： `" + ipinfo_json['org'] + "`"])
                    try:
                        ipinfo_list.extend(
                            ['[' + ipinfo_json['as'] + '](https://bgp.he.net/' + ipinfo_json['as'].split()[0] + ')'])
                    except:
                        pass
                    if ipinfo_json['mobile']:
                        ipinfo_list.extend(['此 IP 可能为**蜂窝移动数据 IP**'])
                    if ipinfo_json['proxy']:
                        ipinfo_list.extend(['此 IP 可能为**代理 IP**'])
                    if ipinfo_json['hosting']:
                        ipinfo_list.extend(['此 IP 可能为**数据中心 IP**'])
                    await context.edit('\n'.join(ipinfo_list))
                    return True
        else:
            url = urlparse(context.arguments)
            if url.hostname:
                url = url.hostname
            else:
                url = url.path
            ipinfo_json = json.loads(requests.get(
                "http://ip-api.com/json/" + url + "?fields=status,message,country,regionName,city,lat,lon,isp,org,as,"
                                                  "mobile,proxy,hosting,query").content.decode(
                "utf-8"))
            if ipinfo_json['status'] == 'fail':
                pass
            elif ipinfo_json['status'] == 'success':
                ipinfo_list = []
                if url == '':
                    ipinfo_list.extend(["查询目标： `本机地址`"])
                else:
                    ipinfo_list.extend(["查询目标： `" + url + "`"])
                if ipinfo_json['query'] == url:
                    pass
                else:
                    ipinfo_list.extend(["解析地址： `" + ipinfo_json['query'] + "`"])
                ipinfo_list.extend(["地区： `" + ipinfo_json['country'] + ' - ' + ipinfo_json['regionName'] + ' - ' +
                                    ipinfo_json['city'] + "`"])
                ipinfo_list.extend(["经纬度： `" + str(ipinfo_json['lat']) + ',' + str(ipinfo_json['lon']) + "`"])
                ipinfo_list.extend(["ISP： `" + ipinfo_json['isp'] + "`"])
                if not ipinfo_json['org'] == '':
                    ipinfo_list.extend(["组织： `" + ipinfo_json['org'] + "`"])
                try:
                    ipinfo_list.extend(
                        ['[' + ipinfo_json['as'] + '](https://bgp.he.net/' + ipinfo_json['as'].split()[0] + ')'])
                except:
                    pass
                if ipinfo_json['mobile']:
                    ipinfo_list.extend(['此 IP 可能为**蜂窝移动数据 IP**'])
                if ipinfo_json['proxy']:
                    ipinfo_list.extend(['此 IP 可能为**代理 IP**'])
                if ipinfo_json['hosting']:
                    ipinfo_list.extend(['此 IP 可能为**数据中心 IP**'])
                await context.edit('\n'.join(ipinfo_list))
                return True
        await context.edit('没有找到要查询的 ip/域名 ...')
    except:
        await context.edit('没有找到要查询的 ip/域名 ...')


@listener(is_plugin=True, outgoing=True, command=alias_command("ipping"),
          description="Ping （或者回复一句话）",
          parameters="<ip/域名>")
async def ipping(context):
    reply = await context.get_reply_message()
    await context.edit('正在查询中...')
    try:
        if reply:
            for num in range(0, len(reply.entities)):
                url = reply.message[reply.entities[num].offset:reply.entities[num].offset + reply.entities[num].length]
                url = urlparse(url)
                if url.hostname:
                    url = url.hostname
                else:
                    url = url.path
                pinginfo = requests.get(
                    "https://steakovercooked.com/api/ping/?host=" + url).content.decode("utf-8")
                if pinginfo == 'null':
                    pass
                elif not pinginfo == 'null':
                    pinginfo = pinginfo.replace('"', '').replace("\/", '/').replace('\\n', '\n', 7).replace('\\n', '')
                    await context.edit(pinginfo)
                    return True
        else:
            url = urlparse(context.arguments)
            if url.hostname:
                url = url.hostname
            else:
                url = url.path
            if url == '':
                await context.edit('没有找到要查询的 ip/域名 ...')
                return True
            pinginfo = requests.get(
                "https://steakovercooked.com/api/ping/?host=" + url).content.decode("utf-8")
            if pinginfo == 'null':
                pass
            elif not pinginfo == 'null':
                pinginfo = pinginfo.replace('"', '').replace("\/", '/').replace('\\n', '\n', 7).replace('\\n', '')
                await context.edit(pinginfo)
                return True
        await context.edit('没有找到要查询的 ip/域名 ...')
    except:
        await context.edit('没有找到要查询的 ip/域名 ...')


@listener(is_plugin=True, outgoing=True, command=alias_command("getdel"),
          description="获取当前群组/频道的死号数。")
async def getdel(context):
    """ PagerMaid getdel. """
    cid = str(context.chat_id)
    pri = cid.startswith('-100')
    parameter = None
    if len(context.parameter) == 1:
        parameter = context.parameter[0]
    if pri:
        member_count = 0
        try:
            await context.edit('遍历成员中。。。')
            chat = await context.get_chat()
            admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
            need_kick = False
            if context.sender in admins:
                need_kick = True
            async for member in bot.iter_participants(chat):
                if member.deleted:
                    member_count += 1
                    if need_kick and parameter:
                        try:
                            await context.client.kick_participant(context.chat_id, member.id)
                        except FloodWaitError:
                            await context.edit('处理失败，您已受到 TG 服务器限制。')
                            return
                        except UserAdminInvalidError:
                            pass
            if need_kick and parameter:
                await context.edit(f'此频道/群组的死号数：`{member_count}`，并且已经清理完毕。')
            else:
                await context.edit(f'此频道/群组的死号数：`{member_count}`。')
        except ChatAdminRequiredError:
            await context.edit('你好像并不拥有封禁用户权限。')
    else:
        await context.edit("请在群组/频道发送。")


@listener(is_plugin=True, outgoing=True, command=alias_command("get_bots"),
          description="获取当前群组/频道的Bot列表。")
async def get_bots(context):
    cid = str(context.chat_id)
    pri = cid.startswith('-100')
    mentions = '以下是当前群组/频道的 Bot 列表：\n'
    admins = []
    members = []
    if pri:
        try:
            await context.edit('遍历成员中。。。')
            async for x in context.client.iter_participants(context.chat, filter=ChannelParticipantsBots):
                if isinstance(x.participant, ChannelParticipantAdmin):
                    admins.append("⚜️ [{}](tg://user?id={})".format(x.first_name, x.id))
                else:
                    members.append("[{}](tg://user?id={})".format(x.first_name, x.id))
            mentions = mentions + '\n'.join(admins) + '\n' + '\n'.join(members)
        except Exception as e:
            mentions += " " + str(e) + "\n"
        await context.edit(mentions)
    else:
        await context.edit("请在群组/频道发送。")
