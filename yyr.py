import json, requests
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("yyr"),
          description="我们都是孙笑川",
          parameters="<字符串>")
async def yyr(context):
    text = context.arguments
    if not text:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return

    try:
        req_data = requests.get("https://github.com/gaowanliang/NMSL/raw/master/src/data/emoji.json").text
    except Exception as e:
        await context.edit("出错了呜呜呜 ~ 无法获取词库。")
        return

    try:
        req_data = json.loads(req_data)
    except Exception as e:
        await context.edit("出错了呜呜呜 ~ 解析JSON时发生了错误。")
        return

    result = text
    for key in sorted(req_data, key=len, reverse=True):
        result = result.replace(key, req_data[key])

    await context.edit(result)
