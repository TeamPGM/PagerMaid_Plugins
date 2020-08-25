import json
import requests
import re
from time import sleep
from pagermaid.listener import listener
from os import remove, path
from collections import defaultdict


@listener(is_plugin=True, outgoing=True, command="music",
          description="网抑云搜歌。",
          parameters="<指令> <关键词>")
async def music(context):
    if len(context.parameter) < 2:
        await context.edit("使用方法：-music <指令> <关键词>\n(指令s为搜索，指令p为播放\n播放时关键词可填歌曲ID，此时为精准播放)")
        return
    else:
        keyword = ''
        for i in range(1, len(context.parameter)):
            keyword += context.parameter[i] + " "
    if context.parameter[0] == "s": #搜索功能
        await context.edit("搜索中 . . .")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36 Edge/15.15063',
                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"}
        url = "http://music.163.com/api/search/pc?&s=" + keyword + "&offset=0&limit=5&type=1"
        for _ in range(20): #最多尝试20次
            status=False
            req = requests.request("GET", url, headers=headers)
            if req.status_code == 200:
                req = json.loads(req.content)
                if req['result']:
                    info=defaultdict()
                    for i in range(len(req['result']['songs'])):
                        info[i]={'id':'', 'title':'', 'alias':'', 'album':'', 'artist':''}
                        info[i]['id']=req['result']['songs'][i]['id']
                        info[i]['title']=req['result']['songs'][i]['name']
                        info[i]['alias']=req['result']['songs'][i]['alias']
                        info[i]['album']=req['result']['songs'][i]['album']['name']
                        for j in range(len(req['result']['songs'][i]['artists'])):
                            info[i]['artist']+=req['result']['songs'][i]['artists'][j]['name'] + " "
                    text="网易云搜索结果如下 \n"
                    for i in range(len(info)):
                        text+=f"{i+1}： \n歌名： {info[i]['title']} \n"
                        if info[i]['alias']:
                            text+=f"别名： {info[i]['alias'][0]} \n"
                        text+=f"专辑： {info[i]['album']} \n作者： {info[i]['artist']}\n歌曲ID： {info[i]['id']} \n\n"
                    await context.edit(text)
                    status=True
                    break
                else:
                    await context.edit("未搜索到结果")
                    status=True
                    break
            else:
                continue
        if status is False:
            await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
            sleep(2)
            await context.delete()
        return
    
    if context.parameter[0] == "p": #播放功能
        await context.edit("获取中 . . .")
        try:
            import eyed3
            imported = True
        except ImportError:
            imported = False
            await context.edit("获取中 . . .\n(eyeD3支持库未安装，歌曲文件信息将无法导入\n请使用-sh pip3 install eyed3安装，或自行ssh安装)")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36 Edge/15.15063',
                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"}
        url = "http://music.163.com/api/search/pc?&s=" + keyword + "&offset=0&limit=1&type=1"
        for _ in range(20): #最多尝试20次
            status=False
            req = requests.request("GET", url, headers=headers)
            if req.status_code == 200:
                req = json.loads(req.content)
                if req['result']:
                    info={'id':'', 'title':'', 'alias':'', 'album':'', 'albumpic':'', 'artist':''}
                    info['id']=req['result']['songs'][0]['id']
                    info['title']=req['result']['songs'][0]['name']
                    info['alias']=req['result']['songs'][0]['alias']
                    info['album']=req['result']['songs'][0]['album']['name']
                    info['albumpic']=req['result']['songs'][0]['album']['picUrl']
                    for j in range(len(req['result']['songs'][0]['artists'])):
                        info['artist']+=req['result']['songs'][0]['artists'][j]['name'] + ";"
                    info['artist']=info['artist'][:-1]
                    music = requests.request("GET", "http://music.163.com/song/media/outer/url?id=" + str(info['id']) +".mp3", headers=headers)
                    name = info['title'] + ".mp3"
                    cap = info['artist'].replace(';',', ') + " - " + info['title']
                    pic = requests.get(info['albumpic'])
                    with open(name, 'wb') as f:
                        f.write(music.content)
                        if (path.getsize(name) / 1024) < 100:
                            remove(name)
                            continue
                        if imported is True:
                            tag = eyed3.load(name).tag
                            tag.encoding = '\x01'
                            tag.artist = info['artist']
                            tag.title = info['title']
                            tag.album = info['album']
                            tag.images.set(3, pic.content, "image/jpeg", u'')
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
                    await context.delete()
                    status = True
                    break
                else:
                    await context.edit("未搜索到结果")
                    status=True
                    break
            else:
                continue
        if status is False:
            await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
            sleep(2)
            await context.delete()
