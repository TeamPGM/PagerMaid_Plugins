from base64 import b64decode, b64encode
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import attach_log, execute, alias_command, obtain_message

@listener(outgoing=True, command=alias_command("b64e"),
          description="将文本转为Base64"
          ,parameters="<text>")
async def b64e(context):
    try:
        msg = await obtain_message(context)
    except:
        return await context.edit("`出错了呜呜呜 ~ 无效的参数。`")

    result = b64encode(msg.encode("utf-8")).decode("utf-8")

    if result:
        if len(result) > 4096:
            return await attach_log(result, context.chat_id, "output.log", context.id)
        await context.edit(f"`{result}`")


@listener(outgoing=True, command=alias_command("b64d"),
          description="将Base64转为文本"
          ,parameters="<text>")
async def b64d(context):
    try:
        msg = await obtain_message(context)
    except:
        return await context.edit("`出错了呜呜呜 ~ 无效的参数。`")
    
    try:
        result = b64decode(msg).decode("utf-8")
    except:
        return await context.edit("`出错了呜呜呜 ~ 无效的参数。`")
    if result:
        if len(result) > 4096:
            return await attach_log(result, context.chat_id, "output.log", context.id)
        await context.edit(f"`{msg}` ==> `{result}`")
