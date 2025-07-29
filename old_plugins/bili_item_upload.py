# -*- coding = utf-8 -*-
# @Python : 3.8
# @Author : 一个魂:@CaroyalKnight
# extra requirements: retry
import asyncio
import json
import re
from os import sep, remove
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import alias_command, pip_install, client

try:
    from retry import retry
except:
    pip_install("retry")
    from retry import retry


@retry(Exception, tries=3, delay=1, backoff=2)
async def get_oid(url):
    find_oid = re.compile(r"(\d+)")
    oid_l = re.findall(r'http.+?://[mt]+?\.bilibili.com.+?/(\d+)', url)
    if len(oid_l) != 0:
        oid = oid_l[0]
    elif re.match(r'http.+?b23.tv/.+?', url):
        req = await client.get(url=url)
        oid = re.findall(find_oid, req.text)[0]
    else:
        oid_l = re.findall(find_oid, url)
        if len(oid_l) != 0 and len(oid_l[0]) > 10:
            oid = oid_l[0]
        else:
            oid = None
    return oid


def gen_tag(text):
    text = str(text)
    r_tag = "#指令 "
    with open(f"data{sep}tags.txt", "r", encoding="utf-8") as f:
        tags = f.read().replace(' ', '').split("\n")
    for tag in tags:
        if tag == "":
            continue
        if tag in text:
            r_tag += f"#{tag} "
    return r_tag


def gen_des(content):
    des = re.sub('@.+?[ |\n]', '', content)  # 去at
    if "@" in des:
        des = re.sub('@.+?$', '', des)  # 去不标准at，可能误杀
    des = re.sub(r'\[.+?\](?!\()', '', des)  # 去表情留markdown_url
    r_tag = gen_tag(des)
    des = re.sub(r'#.+?#', '', des)  # 去标签和换行
    return des, r_tag


@retry(Exception, tries=3, delay=1, backoff=2)
async def get_data(oid):
    params = {'dynamic_id': f'{oid}', }
    req = await client.get('https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/get_dynamic_detail', params=params)
    dict_da = req.json()['data']['card']
    key = dict_da['card'].split('"')[1]
    dict_data = json.loads(dict_da['card'])
    if key == "item":  # 图片动态
        content = dict_data['item']['description']
        pic_urls = [d["img_src"] for d in dict_data['item']['pictures']]  # list
        other = "img"
    elif key == "user":  # 文字动态 or 转发 /data/cards/0/desc/dynamic_id
        try:
            origin = json.loads(dict_data["origin"])
            try:
                content = f"{dict_data['item']['content']}\n转发视频[{origin['title']}](https://b23.tv/av{origin['aid']})"  # str
                pic_urls = [origin["pic"]]  # list  # print(content)
            except KeyError:  # /item/orig_dy_id /item/description
                try:
                    content = f"{dict_data['item']['content']}\n转发动态\n" \
                              f"被转UP:[{dict_data['origin_user']['info']['uname']}]" \
                              f"(https://space.bilibili.com/{dict_data['origin_user']['info']['uid']})\n" \
                              f"[被转动态直达](https://t.bilibili.com/{dict_data['item']['orig_dy_id']})\n" \
                              f"内容：{origin['item']['content']}"  # str
                    pic_urls = []  # list
                except:
                    content = f"{dict_data['item']['content']}\n转发带图动态\n" \
                              f"被转UP:[{dict_data['origin_user']['info']['uname']}]" \
                              f"(https://space.bilibili.com/{dict_data['origin_user']['info']['uid']})\n" \
                              f"[被转动态直达](https://t.bilibili.com/{dict_data['item']['orig_dy_id']})\n" \
                              f"内容：{origin['item']['description']}"
                    pic_urls = [imd["img_src"] for imd in origin['item']['pictures']]  # list /item/pictures/0/img_src
            other = "reprint"
        except Exception as e:
            # print(e)
            content = dict_data['item']['content']
            pic_urls = []  # list
            other = "text"
    elif key == "aid":  # 视频投稿
        id_ = f"https://b23.tv/av{dict_data['aid']}"
        content = f"视频投稿\n{dict_data['dynamic']}\n[{dict_data['title']}]({id_})"
        pic_urls = [dict_data["pic"]]  # list
        other = "av"
    elif key == "id":  # 专栏音频投稿
        id_ = dict_data['id']
        try:
            content = f"专栏投稿\n{dict_data['title']}\n[专栏链接](https://www.bilibili.com/read/cv{id_})"
            pic_urls = [dict_data["banner_url"]]  # list
            other = "cv"
        except:
            content = f"音频投稿\n{dict_data['title']}\n{dict_data['intro']}\n" \
                      f"[音频链接](https://www.bilibili.com/audio/au{id_})"
            pic_urls = [dict_data["cover"]]  # list
            other = "au"
    elif key == "rid":  # 装扮
        content = f"装扮相关\n{dict_data['vest']['content']}"
        pic_urls = []  # list
        other = "decorate"
    else:
        print("     * 注意本条数据 *")
        print(oid)
        raise Exception(f"https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/get_dynamic_detail?dynamic_id={oid}\n"
                        f"出错，此类型无法解析")
    if "user" in dict_data.keys():
        try:
            name = dict_data["user"]["uname"]
        except:
            # print(dict_data)
            name = dict_data["user"]["name"]
        uid = dict_data["user"]["uid"]
    else:  # 投稿
        name = dict_data["owner"]["name"]
        uid = dict_data["owner"]["mid"]
    des, r_tag = gen_des(content)
    return pic_urls, name, uid, des.strip(), r_tag


def save_img(name, data):
    with open(name, "wb") as f:
        f.write(data)


@retry(Exception, tries=3, delay=1, backoff=2)
async def download(url: str):
    name = url.split("/")[-1]
    if name == '':
        return 0
    if "?" in name:
        name = name.split("?")[0]
    try:
        req = await client.get(url)
    except Exception as e:
        return f"{e}"
    save_img(name, req.content)
    return name


@listener(is_plugin=True, outgoing=True, command=alias_command("bup"),
          description="上传B站动态到TG\nUsage: ```-bup <动态url>```\n"
                      "```-bup <atag|dtag|ctag>```\n"
                      "* 关住[嘉然](https://www.bilibili.com/video/BV19Z4y1k7P7)，炖炖解馋", parameters="<url>")
async def bili_item(context):
    # await log(f"触发B站动态上传TG命令,参数:{context.parameter}")
    # 检查文件是否存在不存在则创建
    try:
        with open(f"data{sep}tags.txt", "r", encoding="utf-8") as f:
            pass
    except:
        with open(f"data{sep}tags.txt", "w", encoding="utf-8") as f:
            pass
    if not context.parameter:
        msg = "说明: 上传B站多种动态到TG\nUsage: \n" \
              "* 上传动态:```-bup <url>```\n" \
              "* 增加Tag:```-bup atag <tag1> <tag2>...```\n" \
              "* 删除Tag:```-bup dtag <tag1> <tag2>...```\n" \
              "* 查看Tag:```-bup ctag```\nTag相关参数不带'#'\n" \
              "* 关住[嘉然](https://www.bilibili.com/video/BV19Z4y1k7P7)，炖炖解馋"
        try:
            await context.edit(msg, link_preview=True)
        except Exception as e:
            await context.edit(f"错误信息5秒后自删\n{e}")
            await asyncio.sleep(5)
            await context.delete()
    # 增加tags
    elif context.parameter[0] == "atag":
        if len(context.parameter) == 1:
            await context.edit(f"请在atag后添加tag")
            await asyncio.sleep(5)
            await context.delete()
            return 0
        with open(f"data{sep}tags.txt", "a+", encoding="utf-8") as f:
            mes = ""
            for tag in context.parameter[1:]:
                if tag == "":
                    continue
                f.write(f"{tag}\n")
                mes += f"{tag} "
            await context.edit(f"本次新增Tag如下\n```{mes}```")
            return 0
    # 删除tags
    elif context.parameter[0] == "dtag":
        if len(context.parameter) == 1:
            await context.edit(f"请在dtag后添加tag")
            # await asyncio.sleep(5)
            # await context.delete()
            return 0
        with open(f"data{sep}tags.txt", "r", encoding="utf-8") as f:
            tags = [l.replace("\n", "") for l in f.readlines() if
                    l.replace("\n", "") not in context.parameter[1:] and l.replace("\n", "") != ""]
        with open(f"data{sep}tags.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(tags) + "\n")
            if len(tags) != 0:
                mes = f"删除结束，当前tags如下:\n```{' '.join(tags)}```"
            else:
                mes = f"删除结束，当前tags为空"
            await context.edit(f"{mes}")
            return 0
    # 查询tags
    elif context.parameter[0] == "ctag":
        with open(f"data{sep}tags.txt", "r", encoding="utf-8") as f:
            tags = [l.replace("\n", "") for l in f.readlines()]
        if len(tags) != 0:
            mes = f"查询成功，当前tags如下:\n```{' '.join(tags)}```"
        else:
            mes = f"查询成功，当前tags为空"
        await context.edit(f"{mes}")
        return 0
    # 上传动态
    else:  # context.parameter是个list
        wutu = "https://s2.loli.net/2022/04/14/DFe78jrCTlUfMLd.jpg"
        # wutu = "http://img.yao51.com/jiankangtuku/kmfkwkhpy.jpeg"
        parm = context.parameter
        pic_names = []
        try:
            tasks = []
            try:
                await context.edit("参数已接收,B站动态上传中...")
            except:
                pass
            oid = await asyncio.create_task(get_oid(parm[0]))
            text_add = ""
            if len(parm) >= 2:
                for p in parm[1:]:
                    text_add += f"{p} "
                text_add += "\n"
            if not oid:
                raise Exception("不支持的B站动态链接\n仅支持b23.tv/bilibli.com两种")
            pic_urls, name, uid, des, tags = await asyncio.create_task(get_data(oid))
            if pic_urls:
                for p_u in pic_urls:
                    tasks.append(download(p_u))
                pic_names = await asyncio.gather(*tasks)
                await context.edit("tag生成完毕,图片下载完毕,上传中 . . .")
            else:
                pic_names = [wutu]
            await context.client.send_file(context.chat_id, pic_names if len(pic_names) != 1 else pic_names[0],
                                           caption=f"UP: #{name} [主页](https://space.bilibili.com/{uid})\n"
                                                   f"{des}\n[动态原链接](https://m.bilibili.com/dynamic/{oid})\n"
                                                   f"{text_add}{tags}{'#gif' if 'gif' in pic_names[0] else ''}")
            for pic in pic_names:
                if pic == f"{wutu}":
                    continue
                remove(pic)
        except Exception as e:
            await log(f"动态上传出现错误\n{e}\n点击复制原命令\n```-bup {parm[0]}{(' ' + parm[1]) if len(parm) == 2 else ''}```")
            await asyncio.sleep(5)
        try:
            for pic in pic_names:
                if pic == f"{wutu}":
                    continue
                remove(pic)
        except:
            pass

        await context.delete()  # await log(f"B站动态上传TG命令执行完毕```-bup {parm[0]}{(' ' + parm[1]) if len(parm) == 2 else ''}```")
