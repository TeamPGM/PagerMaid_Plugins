""" Pagermaid hyperlink plugin. by @OahiewUoil """

from pagermaid.listener import listener

@listener(is_plugin=True, outgoing=True, command="hl",
          description="生成隐藏链接。非链接的纯文字将直接隐藏。",
          parameters="<link>")
async def hyperlink(context):
    await context.edit(f"正在生成 . . .")
    if context.arguments:
        link = context.arguments
    await context.edit(f"[ㅤㅤㅤㅤㅤㅤㅤ]({link})", link_preview=False)