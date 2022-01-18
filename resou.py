import json
from requests import get
from json.decoder import JSONDecodeError
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("zhrs"),
          description="知乎热搜。")
async def zhrs(context):
    await context.edit("获取中 . . .")
    req = get("https://tenapi.cn/zhihuresou")
    if req.status_code == 200:
        try:
            data = json.loads(req.text)
        except JSONDecodeError:
            await context.edit("出错了呜呜呜 ~ API 数据解析失败。")
            return
        res = '知乎实时热搜榜：\n'
        for i in range(0, 10):
            res += f'\n{i + 1}.「<a href={data["list"][i]["url"]}>{data["list"][i]["query"]}</a>」'
        await context.edit(res, parse_mode='html', link_preview=False)
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")


@listener(is_plugin=True, outgoing=True, command=alias_command("wbrs"),
          description="微博热搜。")
async def wbrs(context):
    await context.edit("获取中 . . .")
    req = get("https://tenapi.cn/resou")
    if req.status_code == 200:
        try:
            data = json.loads(req.text)
        except JSONDecodeError:
            await context.edit("出错了呜呜呜 ~ API 数据解析失败。")
            return
        res = '微博实时热搜榜：\n'
        for i in range(0, 10):
            res += f'\n{i + 1}.「<a href={data["list"][i]["url"]}>{data["list"][i]["name"]}</a>」  ' \
                   f'热度：{data["list"][i]["hot"]}'
        await context.edit(res, parse_mode='html', link_preview=True)
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")


@listener(is_plugin=True, outgoing=True, command=alias_command("dyrs"),
          description="抖音热搜。")
async def dyrs(context):
    await context.edit("获取中 . . .")
    req = get("https://tenapi.cn/douyinresou")
    if req.status_code == 200:
        try:
            data = json.loads(req.text)
        except JSONDecodeError:
            await context.edit("出错了呜呜呜 ~ API 数据解析失败。")
            return
        res = '抖音实时热搜榜：\n'
        for i in range(0, 10):
            res += f'\n{i + 1}.「{data["list"][i]["name"]}」  热度：{data["list"][i]["hot"]}'
        await context.edit(res, parse_mode='html', link_preview=True)
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")


@listener(is_plugin=True, outgoing=True, command=alias_command("brank"),
          description="B站排行榜。")
async def brank(context):
    await context.edit("获取中 . . .")
    req = get("https://api.imjad.cn/bilibili/v2/?get=rank&type=all")
    if req.status_code == 200:
        try:
            data = json.loads(req.content)['rank']['list']
        except JSONDecodeError:
            await context.edit("出错了呜呜呜 ~ API 数据解析失败。")
            return
        res = 'B站实时排行榜：\n'
        for i in range(0, 10):
            res += f'\n{i + 1}.「<a href="https://www.bilibili.com/video/{data[i]["bvid"]}">{data[i]["title"]}</a>」 - ' \
                   f'{data[i]["author"]}'
        await context.edit(res, parse_mode='html', link_preview=False)
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")
