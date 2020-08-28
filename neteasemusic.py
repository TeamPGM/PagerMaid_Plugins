import json
import requests
import re
import base64
import codecs
import random
import math
from time import sleep
from pagermaid.listener import listener
from pagermaid import bot
from pagermaid.utils import obtain_message
from os import remove, path
from os.path import exists
from collections import defaultdict
from telethon.tl.types import DocumentAttributeAudio


@listener(is_plugin=True, outgoing=True, command="nem",
          description="网易云搜/点歌。\n指令s为搜索，p为点歌，id为歌曲ID点歌\n搜索灰色歌曲请给出歌手\n可回复搜索结果消息`-nem` `p` `<歌曲数字序号>`点歌",
          parameters="<指令> <关键词>")
async def nem(context):
    proxies = {}
    proxynum = 0
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36 Edge/15.15063',
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9", "X-Real-IP": "223.252.199.66"}
    proxy = [{'http': 'http://192.210.137.108:8080', 'https': 'http://192.210.137.108:8080'}, {'http': 'http://music.lolico.me:39000', 'https': 'http://music.lolico.me:39000'},
             {'http': 'http://aimer.one:2333', 'https': 'http://aimer.one:2333'}, {'http': 'http://64.64.250.246:8080', 'https': 'http://64.64.250.246:8080'}]
    if len(context.parameter) < 2:
        await context.edit("**使用方法:** `-nem` `<指令>` `<关键词>`\n\n指令s为搜索，p为点歌，id为歌曲ID点歌\n搜索灰色歌曲请给出歌手\n可回复搜索结果消息`-nem` `p` `<歌曲数字序号>`点歌")
        return
    else:
        keyword = ''
        for i in range(1, len(context.parameter)):
            keyword += context.parameter[i] + " "
    keyword = keyword[:-1]
    idplay = False
    if context.parameter[0] == "id":  # ID点歌功能
        if len(context.parameter) > 2:
            await context.edit("**使用方法:** `-nem` `<指令>` `<关键词>`\n\n指令s为搜索，p为点歌，id为歌曲ID点歌\n搜索灰色歌曲请给出歌手\n可回复搜索结果消息`-nem` `p` `<歌曲数字序号>`点歌")
            return
        idplay = keyword
        context.parameter[0] = "p"
    if context.parameter[0] == "s":  # 搜索功能
        await context.edit(f"【{keyword}】搜索中 . . .")
        url = "http://music.163.com/api/search/pc?&s=" + \
            keyword + "&offset=0&limit=5&type=1"
        for _ in range(20):  # 最多尝试20次
            status = False
            req = requests.request("GET", url, headers=headers)
            if req.status_code == 200:
                req = json.loads(req.content)
                if req['code'] == 200:
                    result = req['result']
                else:
                    result = False
                if result:
                    info = defaultdict()
                    for i in range(len(req['result']['songs'])):
                        info[i] = {'id': '', 'title': '', 'alias': '',
                                   'album': '', 'albumpic': '', 'artist': ''}
                        info[i]['id'] = req['result']['songs'][i]['id']
                        info[i]['title'] = req['result']['songs'][i]['name']
                        info[i]['alias'] = req['result']['songs'][i]['alias']
                        info[i]['album'] = req['result']['songs'][i]['album']['name']
                        info[i]['albumpic'] = req['result']['songs'][i]['album']['picUrl']
                        for j in range(len(req['result']['songs'][i]['artists'])):
                            info[i]['artist'] += req['result']['songs'][i]['artists'][j]['name'] + " "
                    text = f"<strong>关于【{keyword}】的结果如下</strong> \n"
                    for i in range(len(info)):
                        text += f"#{i+1}： \n<strong>歌名</strong>： {info[i]['title']}\n"
                        if info[i]['alias']:
                            text += f"<strong>别名</strong>： <i>{info[i]['alias'][0]}</i>\n"
                        if info[i]['album']:
                            res = '<a href="' + \
                                info[i]['albumpic'] + '">' + \
                                info[i]['album'] + '</a>'
                            text += f"<strong>专辑</strong>： {res} \n"
                        text += f"<strong>作者</strong>： {info[i]['artist']}\n<strong>歌曲ID</strong>： <code>{info[i]['id']}</code>\n————————\n"
                    text += "<strong>回复此消息</strong><code>-nem p <歌曲序号></code><strong>即可点歌</strong>"
                    await context.edit(text, parse_mode='html', link_preview=True)
                    status = True
                    break
                else:
                    await context.edit("**未搜索到结果**")
                    sleep(3)
                    await context.delete()
                    status = True
                    break
            else:
                continue
        if status is False:
            await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
            sleep(3)
            await context.delete()
        return
    elif context.parameter[0] == "p":  # 点歌功能
        try:
            reply = await context.get_reply_message()
        except ValueError:
            await context.edit("出错了呜呜呜 ~ 无效的参数。")
            return
        search = ""
        title = ""
        if reply:
            msg = reply.message
            search = re.findall(".*【(.*)】.*", msg)
            if search:
                try:
                    if int(context.parameter[1]) > 5:
                        await context.edit("出错了呜呜呜 ~ 无效的歌曲序号。")
                        return
                    else:
                        start = "#" + context.parameter[1] + "："
                        search = ".*" + start + "(.*?)" + '————————' + ".*"
                        msg = re.findall(search, msg, re.S)[0]
                        search = ".*歌曲ID： (.*)\n.*"
                        title = ".*歌名： (.*?)\n.*"
                        title = "【"+re.findall(title, msg, re.S)[0]+"】"
                        keyword = re.findall(search, msg, re.S)[0]
                        if reply.sender.is_self:
                            await reply.edit(f"{title}点歌完成")
                except:
                    await context.edit("出错了呜呜呜 ~ 无效的参数。")
                    return
            else:
                await context.edit("出错了呜呜呜 ~ 无效的参数。")
                return

        await context.edit("获取中 . . .")
        try:
            import eyed3
            imported = True
        except ImportError:
            imported = False
            await bot.send_message(context.chat_id, '(`eyeD3`支持库未安装，歌曲文件信息将无法导入\n请使用 `-sh` `pip3` `install` `eyed3` 安装，或自行ssh安装)')
        url = "http://music.163.com/api/search/pc?&s=" + \
            keyword + "&offset=0&limit=1&type=1"
        for _ in range(20):  # 最多尝试20次
            status = False
            if proxynum > (len(proxy) - 1):  # 代理自动切换至下一个
                proxynum = 0
            proxies = proxy[proxynum]
            proxynum += 1
            if idplay:  # 指定ID播放
                idurl = 'https://music.163.com/song?id=' + idplay
                text = requests.get(url=idurl, headers=headers).text
                pattern = re.compile(r'歌曲名《(.*?)》.*?由 (.*?) 演唱.*?')
                keyword = pattern.findall(
                    text)[0][0] + " " + pattern.findall(text)[0][1]
                url = "http://music.163.com/api/search/pc?&s=" + \
                    keyword + "&offset=0&limit=1&type=1"
            # 普通搜索+播放
            req = requests.request("GET", url, headers=headers)
            if req.status_code == 200:
                req = json.loads(req.content)
                if req['result']:
                    info = {'id': '', 'title': '', 'alias': '',
                            'album': '', 'albumpic': '', 'artist': '', 'br': ''}
                    info['id'] = req['result']['songs'][0]['id']
                    info['title'] = req['result']['songs'][0]['name']
                    info['alias'] = req['result']['songs'][0]['alias']
                    info['album'] = req['result']['songs'][0]['album']['name']
                    info['albumpic'] = req['result']['songs'][0]['album']['picUrl']
                    if req['result']['songs'][0]['hMusic']:
                        info['br'] = req['result']['songs'][0]['hMusic']['bitrate']
                    elif req['result']['songs'][0]['mMusic']:
                        info['br'] = req['result']['songs'][0]['mMusic']['bitrate']
                    elif req['result']['songs'][0]['lMusic']:
                        info['br'] = req['result']['songs'][0]['lMusic']['bitrate']
                    for j in range(len(req['result']['songs'][0]['artists'])):
                        info['artist'] += req['result']['songs'][0]['artists'][j]['name'] + ";"
                    info['artist'] = info['artist'][:-1]
                    if title:
                        title = ""
                    else:
                        title = f"【{info['title']}】"
                    await context.edit(f"{title}下载中 . . .")

                    try:
                        from Crypto.Cipher import AES
                        AES.new("0CoJUm6Qyw8W8jud".encode('utf-8'),
                                AES.MODE_CBC, "0102030405060708".encode('utf-8'))
                        ccimported = True
                    except ImportError:
                        ccimported = False
                        await bot.send_message(context.chat_id, '(`PyCryptodome`支持库未安装，音乐曲库/音质受限\n请使用 `-sh` `pip3` `install` `pycryptodome` 安装，或自行ssh安装)')
                    name = info['title'].replace('/', " ") + ".mp3"
                    if ccimported:  # 尝试使用高清音质下载
                        songid = str(info['id'])
                        class WangyiyunDownload(object):
                            def __init__(self):
                                self.key = '0CoJUm6Qyw8W8jud'
                                self.public_key = "010001"
                                self.modulus = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
                                # 偏移量
                                self.iv = "0102030405060708"
                                # 请求头
                                self.headers = {
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
                                    # 传入登录cookie,
                                    'Cookie': 'MUSIC_U=f52f220df171da480dbf33ce89947961585a7fdf08c89a2a4bdd6efebd86544233a649814e309366;',
                                    "X-Real-IP": "223.252.199.66",
                                }
                                # 请求url
                                self.url = 'https://music.163.com/weapi/song/enhance/player/url/v1?csrf_token='

                            # 生成16位随机数字符串
                            def set_random_num(self):
                                random_num = ''
                                # 随机取16个字符
                                string = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                                for ___ in range(16):
                                    n = math.floor(
                                        random.uniform(0, 1) * len(string))
                                    random_num += string[n]
                                # 返回16位随机数字符串
                                return random_num

                            # 生成encSecKey
                            # 通过public_key和modulus对random_num进行RSA加密
                            def RSA_encrypt(self, random_num):
                                # 将16位随机数字符串倒序并以utf-8编码
                                random_num = random_num[::-1].encode('utf-8')
                                # 将其以hex(16进制)编码
                                random_num = codecs.encode(
                                    random_num, 'hex_codec')
                                # 加密(三者均要从16进制转换为10进制)
                                # int(n, 16) --> 将16进制字符串n转换为10进制
                                encryption = int(
                                    random_num, 16) ** int(self.public_key, 16) % int(self.modulus, 16)
                                # 将加密后的数据转换为16进制字符串
                                encryption = format(encryption, 'x')
                                # 返回加密后的字符串
                                return encryption

                            # 生成params
                            # 根据key和iv对msg进行AES加密,需调用两次
                            # key:
                            #   第一次: key
                            #   第二次: random_num
                            # iv: 偏移量iv
                            def AES_encrypt(self, msg, key, iv):
                                # 先将msg按需补全至16的倍数
                                # 需补全的位数
                                pad = (16 - len(msg) % 16)
                                # 补全
                                msg = msg + pad * chr(pad)
                                # 将key,iv和msg均以utf-8编码
                                key = key.encode('utf-8')
                                iv = iv.encode('utf-8')
                                msg = msg.encode('utf-8')
                                # 根据key和iv生成密钥,模式为CBC模式
                                encryptor = AES.new(key, AES.MODE_CBC, iv)
                                # 加密
                                encrypt_aes = encryptor.encrypt(msg)
                                # 先将加密后的值进行base64编码
                                encrypt_text = base64.encodebytes(encrypt_aes)
                                # 将其转换为utf-8字符串
                                encrypt_text = str(encrypt_text, 'utf-8')
                                # 返回加密后的字符串
                                return encrypt_text

                            # 根据歌曲song_id,生成需要传输的data
                            # 其中包括params和encSecKey
                            def construct_data(self, song_id):
                                # 生成16位随机数字符串
                                random_num = self.set_random_num()
                                # 生成encSecKey
                                encSecKey = self.RSA_encrypt(
                                    random_num=random_num)
                                # 调用两次AES加密生成params
                                # 初始化歌曲song_info
                                song_info = '{"ids":"[%s]","level":"exhigh","encodeType":"mp3","csrf_token":"477c1bd99fddedb3adc074f47fee2d35"}' % song_id
                                # 第一次加密,传入encText, key和iv
                                first_encryption = self.AES_encrypt(
                                    msg=song_info, key=self.key, iv=self.iv)
                                # 第二次加密, 传入first_encryption, random_num和iv
                                encText = self.AES_encrypt(
                                    msg=first_encryption, key=random_num, iv=self.iv)
                                # 生成data
                                data = {
                                    'params': encText,
                                    'encSecKey': encSecKey
                                }
                                # 返回data
                                return data

                            # 发送请求,获取下载链接
                            def get_real_url(self):
                                # 输入歌曲song_id
                                self.song_id = songid
                                # 获取data
                                data = self.construct_data(
                                    song_id=self.song_id)
                                # 发送请求
                                request = requests.post(
                                    url=self.url, headers=self.headers, data=data, proxies=proxies, verify=False)
                                # 初始化real_url
                                real_url = ''
                                # 处理返回信息
                                try:
                                    js_text = json.loads(request.text)
                                    data = js_text['data']
                                    if len(data) != 0:
                                        code = data[0]['code']
                                        # 获取成功
                                        if code == 200:
                                            # 歌曲真实地址
                                            real_url = data[0]['url']
                                except:
                                    print('生成的params和encSecKey有误!可重试!')
                                # 返回real_url
                                return real_url

                            def download(self):
                                # 获取下载链接
                                real_url = self.get_real_url()
                                if real_url == '':
                                    print('链接获取失败!')
                                else:
                                    file = name
                                    # 开始下载
                                    content = requests.get(
                                        url=real_url, headers=self.headers).content
                                    with open(file, 'wb') as fp:
                                        fp.write(content)
                        for __ in range(6):  # 最多尝试6次
                            if proxynum > (len(proxy) - 1):  # 代理自动切换至下一个
                                proxynum = 0
                            proxies = proxy[proxynum]
                            proxynum += 1
                            try:
                                WangyiyunDownload().download()
                                ccimported = True
                                break
                            except:
                                ccimported = False
                                continue
                        if not exists(name):
                            ccimported = False

                    if ccimported is False:  # 下载(普通音质)
                        music = requests.request(
                            "GET", "http://music.163.com/api/song/enhance/download/url?&br=" + str(info['br']) + "&id=" + str(info['id']), headers=headers, proxies=proxies, verify=False)
                        if music.status_code == 200:
                            music = json.loads(music.content)
                            if not music['data']['url']:
                                music = requests.request(
                                    "GET", "https://music.163.com/song/media/outer/url?id=" + str(info['id']) + ".mp3", headers=headers, proxies=proxies, verify=False)
                                if music.status_code != 200:
                                    continue
                            else:
                                music = requests.request(
                                    "GET", music['data']['url'], headers=headers)
                        else:
                            continue

                    cap = info['artist'].replace(
                        ';', ', ') + " - " + "**" + info['title'] + "**"

                    if ccimported is False:
                        with open(name, 'wb') as f:
                            f.write(music.content)
                    if (path.getsize(name) / 1024) < 100:
                        remove(name)
                        try:
                            if reply.sender.is_self:
                                await reply.delete()
                        except:
                            pass
                        await context.delete()
                        res = '或者你可以点击<a href="https://music.163.com/#/song?id=' + \
                            str(info['id']) + '">' + \
                            ' <strong>这里</strong> ' + '</a>' + '前往网页版收听'
                        await bot.send_message(context.chat_id, f"<strong>【{info['title']}】</strong>\n" + "歌曲获取失败，资源获取可能受限，你可以再次尝试。\n" + res, parse_mode='html', link_preview=True)
                        return
                    if imported is True:
                        await context.edit(f"{title}信息导入中 . . .")
                        imagedata = requests.get(
                            info['albumpic'], headers=headers).content
                        tag = eyed3.load(name)
                        tag.initTag()
                        tag = tag.tag
                        tag.artist = info['artist']
                        tag.title = info['title']
                        tag.album = info['album']
                        tag.images.remove('')
                        tag.images.set(3, imagedata, "image/jpeg", u"Cover")
                        tag.save(version=eyed3.id3.ID3_DEFAULT_VERSION,
                                 encoding='utf-8')
                    br = ""
                    if imported is True:
                        br = "#" + \
                            str(eyed3.mp3.Mp3AudioFile(
                                name).info.bit_rate[1]) + "kbps "
                    alias = ""
                    if info['alias']:
                        alias = "\n\n__" + info['alias'][0] + "__"
                    cap += "\n#NeteaseMusic " + br + alias
                    await context.edit(f"{title}上传中 . . .")
                    await context.client.send_file(
                        context.chat_id,
                        name,
                        caption=cap,
                        link_preview=False,
                        force_document=False,
                        attributes=(DocumentAttributeAudio(
                            0, False, info['title'], info['artist']),)
                    )
                    try:
                        if reply.sender.is_self:
                            await reply.delete()
                    except:
                        pass
                    try:
                        remove(name)
                    except:
                        pass
                    await context.delete()
                    status = True
                    break
                else:
                    await context.edit("**未搜索到结果**")
                    sleep(3)
                    await context.delete()
                    status = True
                    break
            else:
                continue

        if status is False:
            await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
            sleep(3)
            await context.delete()
    else:  # 错误输入
        await context.edit("**使用方法:** `-nem` `<指令>` `<关键词>`\n\n指令s为搜索，p为点歌，id为歌曲ID点歌\n搜索灰色歌曲请给出歌手\n可回复搜索结果消息`-nem` `p` `<歌曲数字序号>`点歌")
        return
