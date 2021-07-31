from pagermaid.listener import listener
from pagermaid.utils import alias_command

@listener(is_plugin=True, outgoing=True, command=alias_command("square"),
          description="生成文本矩形",
          parameters="<行> <列> <文本>")
async def square(context):
    if not len(context.parameter):
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    hang = context.parameter[0]
    lie = context.parameter[1]
    try:
        hang = int(hang)
        lie = int(lie)
    except ValueError:
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    if hang < 1 or lie < 1:
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    parameters = context.parameter
    del parameters[0]
    del parameters[0]
    text = " ".join(parameters)
    text *=  lie
    text = text.strip()
    result = []
    for i in range(hang):
        result.append(text)
    result = '\n'.join(result)
    if len(result) > 4096:
        await context.edit('出错了呜呜呜 ~ 文本过长。')
    else:
        await context.edit(result)
