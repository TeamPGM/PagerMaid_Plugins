# -*- coding: utf-8 -*-

import base64
from asyncio import sleep
from os import sep, remove, listdir
from os.path import isfile, exists
from time import strftime, localtime

from pagermaid.listener import listener
from pagermaid.utils import alias_command, execute, pip_install

pip_install("pyncm")

from mutagen.mp3 import EasyMP3
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
from pyncm import GetCurrentSession, apis, DumpSessionAsString, SetCurrentSession, LoadSessionFromString
from pyncm.utils.helper import TrackHelper
from pyncm.apis import LoginFailedException
from pyncm.apis.cloudsearch import CloudSearchType
from pyncm.apis.login import LoginLogout

from telethon.tl.types import DocumentAttributeAudio


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


def tag_audio(track, file: str, cover_img: str = ''):
    def write_keys(song):
        # Write trackdatas
        song['title'] = track.TrackName
        song['artist'] = track.Artists
        song['album'] = track.AlbumName
        song['tracknumber'] = str(track.TrackNumber)
        song['date'] = str(track.TrackPublishTime)
        song.save()

    def mp3():
        song = EasyMP3(file)
        write_keys(song)
        if exists(cover_img):
            song = ID3(file)
            song.update_to_v23()  # better compatibility over v2.4
            song.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='',
                          data=open(cover_img, 'rb').read()))
            song.save(v2_version=3)

    def flac():
        song = FLAC(file)
        write_keys(song)
        if exists(cover_img):
            pic = Picture()
            pic.data = open(cover_img, 'rb').read()
            pic.mime = 'image/jpeg'
            song.add_picture(pic)
            song.save()

    def ogg():
        song = OggVorbis(file)
        write_keys(song)
        if exists(cover_img):
            pic = Picture()
            pic.data = open(cover_img, 'rb').read()
            pic.mime = 'image/jpeg'
            song["metadata_block_picture"] = [base64.b64encode(pic.write()).decode('ascii')]
            song.save()

    format_ = file.split('.')[-1].upper()
    for ext, method in [({'MP3'}, mp3), ({'FLAC'}, flac), ({'OGG', 'OGV'}, ogg)]:
        if format_ in ext:
            return method() or True
    return False


async def netease_down(track_info: dict, song_info: dict, song) -> str:
    if not isfile(f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}'):
        # Downloding source audio
        download_by_url(track_info["data"][0]["url"],
                        f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}')
        # Downloading cover
        if not isfile(f'data{sep}{song_info["songs"][0]["name"]}.jpg'):
            download_by_url(song.AlbumCover,
                            f'data{sep}{song_info["songs"][0]["name"]}.jpg')
        # 设置标签
        tag_audio(song, f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}',
                  f'data{sep}{song_info["songs"][0]["name"]}.jpg')
    # 返回
    return f'data{sep}{song_info["songs"][0]["name"]}.{track_info["data"][0]["type"]}'


ned_help_msg = f"""
网易云搜/点歌。

i.e.
`-{alias_command('ned')} 失眠飞行 兔籽鲸 / 雨客Yoker`  # 通过歌曲名称+歌手（可选）点歌
`-{alias_command('ned')} see you again -f`  # 通过 -f 参数点播 flac 最高音质
`-{alias_command('ned')} 1430702717`  # 通过歌曲 ID 点歌
`-{alias_command('ned')} login`  # 显示登录信息
`-{alias_command('ned')} login 手机号码 密码`  # 登录账号
`-{alias_command('ned')} logout`  # 登出
`-{alias_command('ned')} clear`  # 手动清除缓存
"""


@listener(is_plugin=True, outgoing=True, command=alias_command("ned"),
          description=ned_help_msg,
          parameters="{关键词/id}/{login <账号> <密码>}/{clear}")
async def ned(context):
    if len(context.parameter) < 1:
        # 使用方法
        await context.edit(ned_help_msg)
        return
    # 加载登录信息
    if isfile(f"data{sep}session.ncm"):
        with open(f"data{sep}session.ncm") as f:
            SetCurrentSession(LoadSessionFromString(f.read()))
    # 海外用户
    GetCurrentSession().headers['X-Real-IP'] = '118.88.88.88'
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
        time = strftime("%Y-%m-%d %H:%M:%S", localtime(login_info['content']['account']['createTime'] / 1000))
        if context.is_group:
            await context.edit(f"[ned] **登录成功**，已登录{vip_type}账号，账号创建时间：`{time}`")
        else:
            await context.edit(f"[ned] **登录成功**，已登录{vip_type}账号：`{login_info['content']['profile']['nickname']}`，"
                               f"账号创建时间：`{time}`")
        # 保存登录信息
        with open(f"data{sep}session.ncm", 'w+') as f:
            f.write(DumpSessionAsString(GetCurrentSession()))
        return
    elif context.parameter[0] == "logout":
        # 登出
        LoginLogout()
        if isfile(f"data{sep}session.ncm"):
            remove(f"data{sep}session.ncm")
        return await context.edit("[ned] 账号登出成功。")
    elif context.parameter[0] == "clear":
        # 清除歌曲缓存
        for i in listdir("data"):
            if i.find(".mp3") != -1 or i.find(".jpg") != -1 or i.find(".flac") != -1 or i.find(".ogg") != -1:
                remove(f"data{sep}{i}")
        await context.edit("[ned] **已清除缓存**")
        return
    # 搜索歌曲
    # 判断是否使用最高比特率解析
    flac_mode = True if context.arguments.find("-f") != -1 else False
    song_id = context.arguments.replace("-f", "").replace("\u200b", "").strip()
    # id
    if song_id.isdigit():
        song_id = int(song_id)
    else:
        search_data = apis.cloudsearch.GetSearchResult(song_id, CloudSearchType(1), 1)
        if search_data.get("result", {}).get("songCount", 0) >= 1:
            song_id = search_data["result"]["songs"][0]["id"]
        else:
            await context.edit(f"**没有找到歌曲**，请检查歌曲名称是否正确。")
            return
    # 获取歌曲质量是否大于 320k HQ
    track_info = apis.track.GetTrackAudio([song_id], bitrate=3200 * 1000 if flac_mode else 320000)
    # 获取歌曲详情
    song_info = apis.track.GetTrackDetail([song_id])
    if track_info["data"][0]["code"] == 404:
        await context.edit(f"**没有找到歌曲**，请检查歌曲id是否正确。")
        return
    await context.edit(f"正在下载歌曲：**{song_info['songs'][0]['name']} - {gen_author(song_info)}** "
                       f"{round(track_info['data'][0]['size'] / 1000 / 1000, 2)} MB")
    # 下载歌曲并且设置歌曲标签
    song = TrackHelper(song_info['songs'][0])
    # 转义
    for char in song_info["songs"][0]["name"]:
        if char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            song_info["songs"][0]["name"] = song_info["songs"][0]["name"].replace(char, '')
    path = await netease_down(track_info, song_info, song)
    await context.edit("正在上传歌曲。。。")
    # 上传歌曲
    cap_ = ""
    # 提醒登录VIP账号
    if track_info["data"][0]["freeTrialInfo"]:
        cap_ = f"**非VIP，正在试听 {track_info['data'][0]['freeTrialInfo']['start']}s ~ \n" \
               f"{track_info['data'][0]['freeTrialInfo']['end']}s**\n"
    cap = f"「**{song_info['songs'][0]['name']}**」\n" \
          f"{gen_author(song_info)}\n" \
          f"文件大小：{round(track_info['data'][0]['size'] / 1000 / 1000, 2)} MB\n" \
          f"\n{cap_}" \
          f"#netease #{int(track_info['data'][0]['br'] / 1000)}kbps #{track_info['data'][0]['type']}"
    await context.client.send_file(
        context.chat_id,
        path,
        reply_to=context.message.reply_to_msg_id,
        caption=cap,
        link_preview=False,
        force_document=False,
        thumb=f'data{sep}{song_info["songs"][0]["name"]}.jpg',
        attributes=(DocumentAttributeAudio(
            get_duration(song_info, track_info), False, song_info['songs'][0]['name'], gen_author(song_info)),)
    )
    await context.delete()
    # 过多文件自动清理
    if len(listdir("data")) > 100:
        for i in listdir("data"):
            if i.find(".mp3") != -1 or i.find(".jpg") != -1 or i.find(".flac") != -1 or i.find(".ogg") != -1:
                remove(f"data{sep}{i}")
        msg = await context.respond("[ned] **已自动清除缓存**")
        await sleep(3)
        await msg.delete()
