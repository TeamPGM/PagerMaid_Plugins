from time import sleep
from requests import get
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("diss"),
          description="儒雅随和版祖安语录。")
async def diss(context):
    await context.edit("获取中 . . .")
    status = False
    for _ in range(20):  # 最多尝试20次
        req = get("https://nmsl.shadiao.app/api.php?level=min&from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            await context.edit(res, parse_mode='html', link_preview=False)
            status = True
            break
        else:
            continue
    if status == False:
        await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
        sleep(2)
        await context.delete()


@listener(is_plugin=True, outgoing=True, command=alias_command("biss"),
          description="加带力度版祖安语录。")
async def biss(context):
    await context.edit("获取中 . . .")
    status = False
    for _ in range(20):  # 最多尝试20次
        req = get("https://nmsl.shadiao.app/api.php?from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            await context.edit(res, parse_mode='html', link_preview=False)
            status = True
            break
        else:
            continue
    if status == False:
        await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
        sleep(2)
        await context.delete()
