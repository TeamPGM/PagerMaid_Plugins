import json
import requests
from time import sleep
from pagermaid.listener import listener
from os import remove, path
from pagermaid.utils import alias_command, pip_install

pip_install("eyed3")

import eyed3


@listener(is_plugin=True, outgoing=True, command=alias_command("ns"),
          description="随机网抑云热歌。")
async def ns(context):
    await context.edit("获取中 . . .")
    status = False
    for _ in range(20):  # 最多尝试20次
        req = requests.get(
            "http://api.uomg.com/api/rand.music?sort=%E7%83%AD%E6%AD%8C%E6%A6%9C&format=json")
        if req.status_code == 200:
            req = json.loads(req.content)
            try:
                songid = req["data"]["url"][45:]
                music = req['data']['url']
            except KeyError:
                continue
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, '
                                     'like Gecko) Chrome/52.0.2743.116 Safari/537.36 Edge/15.15063',
                       "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,"
                                 "*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"}
            music = requests.request("GET", music, headers=headers)
            name = str(req['data']['name']) + ".mp3"
            with open(name, 'wb') as f:
                f.write(music.content)
                if (path.getsize(name) / 1024) < 100:
                    remove(name)
                    continue
                req = requests.get(
                    "https://api.imjad.cn/cloudmusic/?type=detail&id=" + songid)
                if req.status_code == 200:
                    req = json.loads(req.content)
                    album = req['songs'][0]['al']['name']
                    albumpic = requests.get(req['songs'][0]['al']['picUrl'])
                    artist = req['songs'][0]['ar'][0]['name']
                    title = req['songs'][0]['name']
                    cap = artist + " - " + title
                else:
                    continue
                tag = eyed3.load(name).tag
                tag.encoding = '\x01'
                tag.artist = artist
                tag.title = title
                tag.album = album
                tag.images.set(3, albumpic.content, "image/jpeg", u'')
                tag.save()
                await context.client.send_file(
                    context.chat_id,
                    name,
                    caption=cap,
                    link_preview=False,
                    force_document=False)
            try:
                remove(name)
            except:
                pass
            status = True
            break
        else:
            continue
    if not status:
        await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
        sleep(2)
    await context.delete()
