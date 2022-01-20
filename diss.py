from asyncio import sleep
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command, client


@listener(is_plugin=True, outgoing=True, command=alias_command("diss"),
          description="儒雅随和版祖安语录。")
async def diss(context):
    await context.edit("获取中 . . .")
    for _ in range(20):  # 最多尝试20次
        req = await client.get("https://xtaolabs.com/api/diss/?level=min&from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            return await context.edit(res, parse_mode='html', link_preview=False)
        else:
            continue
    await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
    await sleep(2)
    await context.delete()


@listener(is_plugin=True, outgoing=True, command=alias_command("biss"),
          description="加带力度版祖安语录。")
async def biss(context):
    await context.edit("获取中 . . .")
    for _ in range(20):  # 最多尝试20次
        req = await client.get("https://xtaolabs.com/api/diss/?from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            return await context.edit(res, parse_mode='html', link_preview=False)
        else:
            continue
    await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
    await sleep(2)
    await context.delete()
