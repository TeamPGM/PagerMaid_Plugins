# -*- coding: utf-8 -*-
from asyncio import sleep
from os import sep, remove, listdir
from os.path import isfile
from sys import executable
from time import strftime, localtime

try:
    from mutagen.id3 import ID3, APIC, TIT2, TPE1
    from pyncm import GetCurrentSession, apis, DumpSessionAsString, SetCurrentSession, LoadSessionFromString
    from pyncm.apis import LoginFailedException
    from pyncm.apis.cloudsearch import CloudSearchType

    cc_imported = True
except ImportError:
    print(f'[!] Please run {executable} -m pip install requests pycryptodome tqdm mutagen and '
          f'{executable} -m pip installgit+https://github.com/Xtao-Labs/pyncm.git')
    cc_imported = False


from telethon.tl.types import DocumentAttributeAudio

from pagermaid.listener import listener
from pagermaid.utils import alias_command, execute


def download_by_url(url, dest):
    # Downloads generic content
    response = GetCurrentSession().get(url, stream=True)
    with open(dest, 'wb') as f:
        for chunk in response.iter_content(1024 * 2 ** 10):
            f.write(chunk)  # write every 1MB read
    return dest


def gen_author(song_info: dict) -> str:
    data = []
    for i in song_info["songs"][0]["ar"]:
        data.append(i["name"])
    return " ".join(data)


def get_duration(song_info: dict, track_info: dict) -> int:
    if track_info["data"][0]["freeTrialInfo"]:
        return track_info["data"][0]["freeTrialInfo"]["end"] - track_info["data"][0]["freeTrialInfo"]["start"]
    else:
        return int(song_info["songs"][0]["dt"] / 1000)


async def netease_down(track_info: dict, song_info: dict) -> str:
    if not isfile(f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}'):
        # Downloding source audio
        download_by_url(track_info["data"][0]["url"],
                        f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}')
        # Downloading cover
        download_by_url(song_info["songs"][0]["al"]["picUrl"],
                        f'data{sep}{song_info["songs"][0]["name"]}.jpg')
        with open(f'data{sep}{song_info["songs"][0]["name"]}.jpg', 'rb') as f:
            picData = f.read()
        # 设置标签
        info = {'picData': picData,
                'title': song_info["songs"][0]["name"],
                'artist': gen_author(song_info)}
        songFile = ID3(f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}')
        songFile['APIC'] = APIC(  # 插入封面
            encoding=3,
            mime='image/jpeg',
            type=3,
            desc=u'Cover',
            data=info['picData']
        )
        songFile['TIT2'] = TIT2(  # 插入歌名
            encoding=3,
            text=info['title']
        )
        songFile['TPE1'] = TPE1(  # 插入第一演奏家、歌手、等
            encoding=3,
            text=info['artist']
        )
        songFile.save()
    # 返回
    return f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}'


ned_help_msg = f"""
网易云搜/点歌。

i.e.
`-{alias_command('ned')} 失眠飞行 兔籽鲸 / 雨客Yoker`  # 通过歌曲名称+歌手（可选）点歌
`-{alias_command('ned')} 1430702717`  # 通过歌曲 ID 点歌
`-{alias_command('ned')} login`  # 显示登录信息
`-{alias_command('ned')} login 手机号码 密码`  # 登录账号
`-{alias_command('ned')} clear`  # 手动清除缓存
"""


@listener(is_plugin=True, outgoing=True, command=alias_command("ned"),
          description=ned_help_msg,
          parameters="{关键词/id}/{login <账号> <密码>}/{clear}")
async def ned(context):
    if not cc_imported:
        await context.edit(f"[!] Please run `-sh {executable} -m pip install requests pycryptodome tqdm mutagen` "
                           f"and run `-sh {executable} -m pip install git+https://github.com/Xtao-Labs/pyncm.git` "
                           f"and then restart pagermaid.")
        return
    if len(context.parameter) < 1:
        # 使用方法
        await context.edit(ned_help_msg)
        return
    # 加载登录信息
    if isfile(f"data{sep}session.ncm"):
        with open(f"data{sep}session.ncm") as f:
            SetCurrentSession(LoadSessionFromString(f.read()))
    # 处理账号登录
    if context.parameter[0] == "login":
        # 显示登录信息
        if len(context.parameter) == 1:
            login_info = GetCurrentSession().login_info
            if login_info["success"]:
                # 获取VIP类型
                if login_info['content']['account']['vipType'] != 0:
                    vip_type = "**VIP**"
                else:
                    vip_type = "**普通**"
                # 获取账号创建时间
                time = strftime("%Y-%m-%d %H:%M:%S", localtime(login_info['content']['account']['createTime'] / 1000))
                if context.is_group:
                    await context.edit(f"[ned] 已登录{vip_type}账号，账号创建时间：`{time}`")
                else:
                    await context.edit(f"[ned] 已登录{vip_type}账号：`{login_info['content']['profile']['nickname']}`，"
                                       f"账号创建时间：`{time}`")
            else:
                await context.edit(f"[ned] **未登录/登录失败**，额外信息：`{login_info['content']}`")
            return
        # 过滤空参数
        if len(context.parameter) == 2:
            # 登录命令格式错误
            await context.edit(f"**使用方法:** `-{alias_command('ned')} <账号> <密码>`")
            return
        # 开始登录
        try:
            apis.login.LoginViaCellphone(context.parameter[1], context.parameter[2])
        except LoginFailedException:
            await context.edit("**登录失败**，请检查账号密码是否正确。")
            return
        # 获取登录信息
        login_info = GetCurrentSession().login_info
        # 获取VIP类型
        if login_info['content']['account']['vipType'] != 0:
            vip_type = "**VIP**"
        else:
            vip_type = "**普通**"
        # 获取账号创建时间
        time = strftime("%Y-%m-%d %H:%M:%S", localtime(login_info['content']['account']['createTime']/1000))
        if context.is_group:
            await context.edit(f"[ned] **登录成功**，已登录{vip_type}账号，账号创建时间：`{time}`")
        else:
            await context.edit(f"[ned] **登录成功**，已登录{vip_type}账号：`{login_info['content']['profile']['nickname']}`，"
                               f"账号创建时间：`{time}`")
        # 保存登录信息
        with open(f"data{sep}session.ncm", 'w+') as f:
            f.write(DumpSessionAsString(GetCurrentSession()))
        return
    if context.parameter[0] == "clear":
        # 清除歌曲缓存
        for i in listdir("data"):
            if i.find(".mp3") != -1 or i.find(".jpg") != -1:
                remove(f"data{sep}{i}")
        await context.edit("**已清除缓存**")
        return
    # 搜索歌曲
    song_id = context.arguments
    # id
    if song_id.isdigit():
        song_id = int(song_id)
    else:
        search_data = apis.cloudsearch.GetSearchResult(song_id, CloudSearchType(1), 1)
        if len(search_data["result"]["songs"]) == 1:
            song_id = search_data["result"]["songs"][0]["id"]
        else:
            await context.edit(f"**没有找到歌曲**，请检查歌曲名称是否正确。")
            return
    # 获取歌曲信息小于等于 320k HQ
    track_info = apis.track.GetTrackAudio([song_id])
    # 获取歌曲详情
    song_info = apis.track.GetTrackDetail([song_id])
    if track_info["data"][0]["code"] == 404:
        await context.edit(f"**没有找到歌曲**，请检查歌曲id是否正确。")
        return
    await context.edit(f"正在下载歌曲：**{song_info['songs'][0]['name']} - {gen_author(song_info)}**")
    # 下载歌曲并且设置歌曲标签
    path = await netease_down(track_info, song_info)
    await context.edit("正在上传歌曲。。。")
    # 上传歌曲
    cap_ = ""
    # 提醒登录VIP账号
    if track_info["data"][0]["freeTrialInfo"]:
        cap_ = f"**非VIP，正在试听 {track_info['data'][0]['freeTrialInfo']['start']}s ~ " \
               f"{track_info['data'][0]['freeTrialInfo']['end']}s**\n"
    cap = f"「**{song_info['songs'][0]['name']}**」\n" \
          f"{gen_author(song_info)}\n" \
          f"\n{cap_}" \
          f"#netease #{int(track_info['data'][0]['br'] / 1000)}kbps #{track_info['data'][0]['type']}"
    await context.client.send_file(
        context.chat_id,
        path,
        caption=cap,
        link_preview=False,
        force_document=False,
        thumb=path[:-3] + 'jpg',
        attributes=(DocumentAttributeAudio(
            get_duration(song_info, track_info), False, song_info['songs'][0]['name'], gen_author(song_info)),)
    )
    await context.delete()
    # 过多文件自动清理
    if len(listdir("data")) > 100:
        for i in listdir("data"):
            if i.find(".mp3") != -1 or i.find(".jpg") != -1:
                remove(f"data{sep}{i}")
        msg = await context.respond("**已清除缓存**")
        await sleep(3)
        await msg.delete()
