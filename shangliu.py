from time import sleep
from requests import get
from pagermaid.listener import listener

@listener(is_plugin=True, outgoing=True, command="chp",
          description="彩虹屁生成器。")
async def chp(context):
    await context.edit("获取中 . . .")
    status=False
    for _ in range(20): #最多尝试20次
        req = get("https://chp.shadiao.app/api.php?from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            await context.edit(res, parse_mode='html', link_preview=False)
            status=True
            break
        else:
            continue
    if status == False:
        await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
        sleep(2)
        await context.delete()

@listener(is_plugin=True, outgoing=True, command="djt",
          description="毒鸡汤生成器。")
async def djt(context):
    await context.edit("获取中 . . .")
    status=False
    for _ in range(20): #最多尝试20次
        req = get("https://du.shadiao.app/api.php?from=tntcrafthim")
        if req.status_code == 200:
            res = req.text
            await context.edit(res, parse_mode='html', link_preview=False)
            status=True
            break
        else:
            continue
    if status == False:
        await context.edit("出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
        sleep(2)
        await context.delete()

@listener(is_plugin=True, outgoing=True, command="yxh",
          description="营销号文案生成器（建议配合tts食用）。",
          parameters="<主体> <事件> <原因>")
async def yxh(context):
    await context.edit("生成中 . . .")
    req = get("https://du.shadiao.app/api.php?from=tntcrafthim")
    await context.edit(f"{context.parameter[0]}{context.parameter[1]}是怎么回事呢？{context.parameter[0]}相信大家都很熟悉，但是{context.parameter[0]}{context.parameter[1]}是怎么回事呢，下面就让小编带大家一起了解吧。\n{context.parameter[0]}{context.parameter[1]}，其实就是{context.parameter[2]}，大家可能会很惊讶{context.parameter[0]}怎么会{context.parameter[1]}呢？但事实就是这样，小编也感到非常惊讶。\n这就是关于{context.parameter[0]}{context.parameter[1]}的事情了，大家有什么想法呢，欢迎在评论区告诉小编一起讨论哦！")