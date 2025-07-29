from enum import Enum
from typing import Dict, Any

from pagermaid.enums import Message
from pagermaid.enums.command import CommandHandler
from pagermaid.listener import listener
from pagermaid.services import client


class TypeEnum(str, Enum):
    ZHIHU = "知乎"
    WB = "微博"
    DY = "抖音"
    BAIDU = "百度"
    B = "哔哩哔哩"
    TT = "今日头条"


RESOU_HELP = """热搜榜单

- 参数 zhihu 查询知乎热搜
- 参数 wb 查询微博热搜
- 参数 dy 查询抖音热搜
- 参数 baidu 查询百度热搜
- 参数 b 查询哔哩哔哩
- 参数 tt 查询今日头条热点
"""
RESOU_MAP = {
    TypeEnum.ZHIHU: "https://tenapi.cn/v2/zhihuhot",
    TypeEnum.WB: "https://tenapi.cn/v2/weibohot",
    TypeEnum.DY: "https://tenapi.cn/v2/douyinhot",
    TypeEnum.BAIDU: "https://tenapi.cn/v2/baiduhot",
    TypeEnum.B: "https://tenapi.cn/v2/bilihot",
    TypeEnum.TT: "https://tenapi.cn/v2/toutiaohot"
}


async def get_data(name_type: TypeEnum) -> Dict[str, Any]:
    url = RESOU_MAP.get(name_type)
    try:
        data = (await client.get(url)).json()["data"]
    except Exception as e:
        return {"error": str(e)}
    res = ""
    for i, d in enumerate(data):
        if i == 10:
            break
        res += f"\n{i + 1}. 「<a href={d['url']}>{d['name']}</a>」"
    return {"error": None, "data": data, "text": res}


@listener(command="resou", description="热搜榜单查询")
async def resou_handler(message: Message):
    await message.edit(RESOU_HELP)


resou_handler: "CommandHandler"


async def rs_handler(message: Message, name_type: TypeEnum):
    data = await get_data(name_type)
    if data.get("error"):
        await message.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")
        return
    res = f"{name_type.value}实时热搜榜：\n{data['text']}"
    await message.edit(res)


@resou_handler.sub_command(command="zhihu", description="知乎热搜")
async def zhrs(message: Message):
    await rs_handler(message, TypeEnum.ZHIHU)


@resou_handler.sub_command(command="wb", description="微博热搜。")
async def wbrs(message: Message):
    await rs_handler(message, TypeEnum.WB)


@resou_handler.sub_command(command="dy", description="抖音热搜。")
async def dyrs(message: Message):
    await rs_handler(message, TypeEnum.DY)


@resou_handler.sub_command(command="baidu", description="百度热搜。")
async def bdrs(message: Message):
    await rs_handler(message, TypeEnum.BAIDU)


@resou_handler.sub_command(command="b", description="哔哩哔哩热搜。")
async def brs(message: Message):
    await rs_handler(message, TypeEnum.B)


@resou_handler.sub_command(command="tt", description="今日头条热点。")
async def ttrs(message: Message):
    await rs_handler(message, TypeEnum.TT)
