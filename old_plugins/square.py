from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid import version


@listener(is_plugin=True, outgoing=True, command=alias_command("square"),
          description="生成文本矩形",
          parameters="<文本> <行> <列>")
async def square(context):
    if not len(context.parameter) > 2:
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    parameters = context.parameter[-2:]
    hang = parameters[0]
    lie = parameters[1]
    try:
        hang = int(hang)
        lie = int(lie)
    except ValueError:
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    if hang < 1 or lie < 1:
        await context.edit('出错了呜呜呜 ~ 参数错误。')
        return
    parameters = [i for i in context.parameter if i not in parameters]
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
