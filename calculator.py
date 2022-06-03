from pagermaid.listener import listener
from pagermaid.utils import attach_log, execute, alias_command


@listener(is_plugin=False, outgoing=True, command=alias_command("cal"),
          description="计算\n示例：\n`-cal 1+1`加法\n`-cal 2-1`减法\n`-cal 1*2`乘法\n`-cal 4/2`除法\n`-cal 4^2`幂运算\n`-cal sqrt(4)`开方",
          parameters="<基本运算>")
async def cal(context):
    command = context.arguments
    if context.is_channel and not context.is_group:
        await context.edit("`出错了呜呜呜 ~ 当前 PagerMaid-Modify 的配置禁止在频道中执行此命令。`")
        return

    if not command:
        await context.edit("`出错了呜呜呜 ~ 无效的参数。`")
        return

    await context.edit(f"{command}")
    cmd = f'echo "scale=4;{command}" | bc'
    result = await execute(cmd)

    if result:
        if len(result) > 4096:
            await attach_log(result, context.chat_id, "output.log", context.id)
            return

        await context.edit(f"{command}=\n`{result}`")
    else:
        return

@listener(is_plugin=False, outgoing=True, command=alias_command("con"),
            description="换算\n示例：\n`-con 2 99`将99转换为2进制",
            parameters="<进制(数字)> <数值>")
async def con(context):
    command = context.arguments.split()
    if context.is_channel and not context.is_group:
        await context.edit("`出错了呜呜呜 ~ 当前 PagerMaid-Modify 的配置禁止在频道中执行此命令。`")
        return

    if not command:
        await context.edit("`出错了呜呜呜 ~ 无效的参数。`")
        return

    obase = command[0].upper().strip()
    num = command[1].upper().strip()
    await context.edit(f"{num}")
    cmd = f'echo "obase={obase};{num}" | bc'
    result = await execute(cmd)

    if result:
        if len(result) > 4096:
            await attach_log(result, context.chat_id, "output.log", context.id)
            return

        await context.edit(f"{num}=\n`{result}`\n{obase}进制")
    else:
        return