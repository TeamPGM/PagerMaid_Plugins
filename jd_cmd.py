""" PagerMaid module to handle jd command. """

from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import lang, alias_command, obtain_message, client


@listener(is_plugin=False, outgoing=True, command=alias_command("jd_cmd"),
          description="解析 JD 口令",
          parameters="<JD 口令>")
async def jd_cmd(context):
    try:
        text = await obtain_message(context)
    except ValueError:
        return await context.edit("[jd_cmd] " + lang("msg_ValueError"))
    try:
        data = (await client.post("https://api.jds.codes/jCommand", json={"code": text})).json()
    except:
        return await context.edit("[jd_cmd] 网络错误！")
    if data["code"] != 200:
        return await context.edit("[jd_cmd] 未找到 JD 口令！")
    try:
        data = data["data"]
        await context.edit(f"【jd_cmd】 [【{data['title']}】 - {data['userName']}]({data['jumpUrl']})")
    except KeyError:
        return await context.edit("[jd_cmd] 数据错误！")
