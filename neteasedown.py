# -*- coding: utf-8 -*-
import os
import re
import binascii
import base64
import json
import copy
import requests
from sys import executable
from os.path import exists
from telethon.tl.types import DocumentAttributeAudio
from pagermaid.listener import listener
from pagermaid.utils import alias_command

fake_headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",  # noqa
                "Accept-Charset": "UTF-8,*;q=0.5",
                "Accept-Encoding": "gzip,deflate,sdch",
                "Accept-Language": "en-US,en;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:60.0) Gecko/20100101 Firefox/60.0",  # noqa
                "referer": "https://www.google.com"}
wget_headers = {"Accept": "*/*",
                "Accept-Encoding": "identity",
                "User-Agent": "Wget/1.19.5 (darwin17.5.0)"}

try:
    from Crypto.Cipher import AES

    AES.new("0CoJUm6Qyw8W8jud".encode('utf-8'),
            AES.MODE_CBC, "0102030405060708".encode('utf-8'))
    cc_imported = True
except ImportError:
    cc_imported = False
try:
    import eyed3

    eyed3_imported = True
except ImportError:
    eyed3_imported = False


class DataError(RuntimeError):
    """ 得到的data中没有预期的内容 """

    def __init__(self, *args, **kwargs):
        pass


class MusicApi:
    # class property
    # 子类修改时使用 deepcopy
    def __init__(self):
        pass

    session = requests.Session()
    session.headers.update(fake_headers)

    @classmethod
    def request(cls, url, method="POST", data=None):
        if method == "GET":
            resp = cls.session.get(url, params=data, timeout=7)
        else:
            resp = cls.session.post(url, data=data, timeout=7)
        if resp.status_code != requests.codes.ok:
            raise RequestError(resp.text)
        if not resp.text:
            raise ResponseError("No response data.")
        return resp.json()


class NeteaseApi(MusicApi):
    session = copy.deepcopy(MusicApi.session)
    session.headers.update({"referer": "http://music.163.com/"})

    @classmethod
    def encode_netease_data(cls, data) -> str:
        data = json.dumps(data)
        key = binascii.unhexlify("7246674226682325323F5E6544673A51")
        encryptor = AES.new(key, AES.MODE_ECB)
        # 补足data长度，使其是16的倍数
        pad = 16 - len(data) % 16
        fix = chr(pad) * pad
        byte_data = (data + fix).encode("utf-8")
        return binascii.hexlify(encryptor.encrypt(byte_data)).upper().decode()

    @classmethod
    def encrypted_request(cls, data) -> dict:
        MODULUS = (
            "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
            "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280"
            "104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932"
            "575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b"
            "3ece0462db0a22b8e7"
        )
        PUBKEY = "010001"
        NONCE = b"0CoJUm6Qyw8W8jud"
        data = json.dumps(data).encode("utf-8")
        secret = cls.create_key(16)
        params = cls.aes(cls.aes(data, NONCE), secret)
        encseckey = cls.rsa(secret, PUBKEY, MODULUS)
        return {"params": params, "encSecKey": encseckey}

    @classmethod
    def aes(cls, text, key):
        pad = 16 - len(text) % 16
        text = text + bytearray([pad] * pad)
        encryptor = AES.new(key, 2, b"0102030405060708")
        ciphertext = encryptor.encrypt(text)
        return base64.b64encode(ciphertext)

    @classmethod
    def rsa(cls, text, pubkey, modulus):
        text = text[::-1]
        rs = pow(int(binascii.hexlify(text), 16), int(pubkey, 16), int(modulus, 16))
        return format(rs, "x").zfill(256)

    @classmethod
    def create_key(cls, size):
        return binascii.hexlify(os.urandom(size))[:16]


def netease_search(keyword) -> list:
    eparams = {
        "method": "POST",
        "url": "http://music.163.com/api/cloudsearch/pc",
        "params": {"s": keyword, "type": 1, "offset": 0, "limit": 5},
    }
    data = {"eparams": NeteaseApi.encode_netease_data(eparams)}

    songs_list = []
    res_data = (
        NeteaseApi.request(
            "http://music.163.com/api/linux/forward", method="POST", data=data
        )
            .get("result", {})
            .get("songs", {})
    )
    try:
        for item in res_data:
            if item.get("privilege", {}).get("fl", {}) == 0:
                # 没有版权
                continue
            # 获得歌手名字
            singers = [s.get("name", "") for s in item.get("ar", [])]
            # 获得音乐的文件大小
            # TODO: 获取到的大小并不准确，考虑逐一获取歌曲详情
            if item.get("privilege", {}).get("fl", {}) >= 320000 and item.get("h", ""):
                size = item.get("h", {}).get("size", 0)
            elif item.get("privilege", {}).get("fl", {}) >= 192000 and item.get(
                    "m", ""
            ):
                size = item.get("m", {}).get("size", 0)
            else:
                size = item.get("l", {}).get("size", 0)

            song = {"id": item.get("id", ""),
                    "title": item.get("name", ""),
                    "singer": "、".join(singers),
                    "album": item.get("al", {}).get("name", ""),
                    "duration": int(item.get("dt", 0) / 1000),
                    "size": round(size / 1048576, 2),
                    "cover_url": item.get("al", {}).get("picUrl", "")}
            songs_list.append(song)
    except Exception as e:
        raise DataError(e)

    return songs_list


def netease_down(info):
    try:
        imagedata = requests.get(info['cover_url'], headers=wget_headers).content
        if not exists('data/' + info['title'] + '.mp3'):
            r = requests.get(
                info['song_url'],
                stream=True,
                headers=wget_headers,
            )
            with open('data/' + info['title'] + '.mp3', "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            tag = eyed3.load(info['title'] + '.mp3')
            tag.initTag()
            tag = tag.tag
            tag.artist = info['singer']
            tag.title = info['title']
            tag.album = info['album']
            tag.images.remove('')
            tag.images.set(6, imagedata, "image/jpeg", u"Media")
            tag.save(version=eyed3.id3.ID3_DEFAULT_VERSION, encoding='utf-8')
        return imagedata
    except Exception as e:
        raise DataError


def netease_single(id):
    song_id = id
    data_detail = NeteaseApi.encrypted_request(
        dict(c=json.dumps([{"id": song_id}]), ids=[song_id])
    )
    res_data_detail = NeteaseApi.request(
        "http://music.163.com/weapi/v3/song/detail", method="POST", data=data_detail
    ).get("songs", [])
    data = NeteaseApi.encrypted_request(dict(ids=[song_id], br=32000))
    res_data = NeteaseApi.request(
        "http://music.163.com/weapi/song/enhance/player/url",
        method="POST",
        data=data,
    ).get("data", [])
    if len(res_data_detail) > 0 and len(res_data) > 0:
        item = res_data_detail[0]
        singers = [s.get("name", "") for s in item.get("ar", {})]
        song = {"id": item.get("id", ""),
                "title": item.get("name", ""),
                "singers": singers,
                "singer": "、".join(singers),
                "album": item.get("al", {}).get("name", ""),
                "duration": int(item.get("dt", 0) / 1000),
                "cover_url": item.get("al", {}).get("picUrl", ""),
                "song_url": res_data[0].get("url", ""),
                "rate": int(res_data[0].get("br", 0) / 1000)}
        return song
    else:
        raise DataError("Get song detail failed.")


@listener(is_plugin=True, outgoing=True, command=alias_command("ned"),
          description="网易云搜/点歌。",
          parameters="<关键词/id>")
async def ned(context):
    if len(context.parameter) < 1:
        await context.edit("**使用方法:** `-ned` `<关键词/id>`")
        return
    else:
        if not eyed3_imported and not cc_imported:
            try:
                await context.edit("支持库 `eyed3` `PyCryptodome` 未安装...\n正在尝试自动安装...")
                await execute(f'{executable} -m pip install eyed3')
                await execute(f'{executable} -m pip install pycryptodome')
                await sleep(10)
                result = await execute(f'{executable} -m pip show eyed3')
                result_1 = await execute(f'{executable} -m pip show pycryptodome')
                if len(result) > 0 and len(result_1) > 0:
                    await context.edit('支持库 `eyed3` `pycryptodome` 安装成功...\n正在尝试自动重启...')
                    await context.client.disconnect()
                else:
                    await context.edit(
                        f"自动安装失败..\n请尝试手动安装 `-sh {executable} -m pip install eyed3` 和 "
                        f"`-sh {executable} -m pip install pycryptodome` 随后，请重启 PagerMaid-Modify 。")
                    return
            except:
                return
        type = 'keyword'
        id = context.parameter[0]
        # 测试是否为 id
        try:
            id = int(id)
            type = 'id'
        except ValueError:
            pass
        if type == 'keyword':
            # 开始搜歌
            await context.edit(f"【{id}】搜索中 . . .")
            try:
                info = netease_search(id)
            except DataError:
                await context.edit(f"【{id}】搜索失败。")
                return
            if len(info) > 0:
                text = f"<strong>关于【{id}】的结果如下</strong> \n"
                for i in range(len(info)):
                    text += f"#{i + 1}： \n<strong>歌名</strong>： {info[i]['title']}\n"
                    if info[i]['album']:
                        res = '<a href="' + \
                              info[i]['cover_url'] + '">' + \
                              info[i]['album'] + '</a>'
                        text += f"<strong>专辑</strong>： {res} \n"
                    text += f"<strong>作者</strong>： {info[i]['singer']}\n" \
                            f"<strong>歌曲ID</strong>： <code>{info[i]['id']}</code>\n————————\n"
                await context.edit(text, parse_mode='html', link_preview=True)
            else:
                await context.edit("**未搜索到结果**")
                sleep(3)
                await context.delete()
            return
        elif type == 'id':
            # 开始点歌
            # 检查 id 是否为 1-5
            try:
                reply = await context.get_reply_message()
            except ValueError:
                await context.edit("出错了呜呜呜 ~ 无效的参数。")
                return
            if reply and 0 < id < 6:
                msg = reply.message
                search = re.findall(".*【(.*)】.*", msg)
                if search:
                    try:
                        start = "#" + context.parameter[0] + "："
                        search = ".*" + start + "(.*?)" + '————————' + ".*"
                        msg = re.findall(search, msg, re.S)[0]
                        search = ".*歌曲ID： (.*)\n.*"
                        title = ".*歌名： (.*?)\n.*"
                        title = "【" + re.findall(title, msg, re.S)[0] + "】"
                        id = re.findall(search, msg, re.S)[0]
                        if reply.sender.is_self:
                            await reply.edit(f"{title}点歌完成")
                    except:
                        await context.edit("出错了呜呜呜 ~ 无效的歌曲序号。")
                        return
                else:
                    await context.edit("出错了呜呜呜 ~ 无效的参数。")
                    return
            await context.edit("获取中 . . .")
            try:
                data = netease_single(id)
                await context.edit(f"【{data['title']}】下载中 . . .")
                img_data = netease_down(data)
            except DataError:
                await context.edit(f"【{id}】获取失败。")
                return
            await context.edit(f"【{data['title']}】发送中 . . .")
            cap = data['singer'] + " - " + "**" + data['title'] + f"**\n#NeteaseMusic #{data['rate']}kbps "
            if not exists("plugins/NeteaseMusicExtra/FastTelethon.py"):
                if not exists("plugins/NeteaseMusicExtra"):
                    os.mkdir("plugins/NeteaseMusicExtra")
                faster = requests.request(
                    "GET", "https://gist.githubusercontent.com/TNTcraftHIM"
                           "/ca2e6066ed5892f67947eb2289dd6439/raw"
                           "/86244b02c7824a3ca32ce01b2649f5d9badd2e49/FastTelethon.py")
                if faster.status_code == 200:
                    with open("plugins/NeteaseMusicExtra/FastTelethon.py", "wb") as f:
                        f.write(faster.content)
                else:
                    pass
            try:
                from NeteaseMusicExtra.FastTelethon import upload_file
                file = await upload_file(context.client, open('data/' + data['title'] + '.mp3', 'rb'),
                                         'data/' + data['title'] + '.mp3')
            except:
                file = 'data/' + data['title'] + '.mp3'
                if not exists("plugins/NeteaseMusicExtra/NoFastTelethon.txt"):
                    with open("plugins/NeteaseMusicExtra/NoFastTelethon.txt", "w") as f:
                        f.write("此文件出现表示 FastTelethon 支持文件在首次运行 NeteaseMusic 插件时导入失败\n这可能是因为Github"
                                "服务器暂时性的访问出错导致的\nFastTelethon可以提升低网络性能机型在上传文件时的效率，但是正常情况提升并不明显\n"
                                "如想要手动导入，可以手动下载：\nhttps://gist.githubusercontent.com/TNTcraftHIM"
                                "/ca2e6066ed5892f67947eb2289dd6439/raw"
                                "/86244b02c7824a3ca32ce01b2649f5d9badd2e49/FastTelethon.py\n并放入当前文件夹")
                    await bot.send_message(context.chat_id, '`FastTelethon`支持文件导入失败，上传速度可能受到影响\n'
                                                            '此提示仅出现**一次**，手动导入可参考：\n`' + os.getcwd() +
                                           '/plugins/NeteaseMusicExtra/NoFastTelethon.txt`')
            await context.client.send_file(
                context.chat_id,
                file,
                caption=cap,
                link_preview=False,
                force_document=False,
                thumb=img_data,
                attributes=(DocumentAttributeAudio(
                    data['duration'], False, data['title'], data['singer']),)
            )
            await context.delete()
            return
