from pagermaid import version, silent
from pagermaid.listener import listener
from pagermaid.utils import alias_command, client
from os import sep, remove


@listener(is_plugin=True, outgoing=True, command=alias_command("everyday_en"),
          description="每日一句英文句子")
async def everyday(context):
    if not silent:
        await context.edit("获取中 . . .")
    try:
        data = await client.get("https://open.iciba.com/dsapi/")
        data = data.json()
        img = await client.get(data["fenxiang_img"])
        with open(f"data{sep}everyday.jpg", 'wb') as f:
            f.write(img.content)
        await context.edit("上传中 . . .")
        await context.client.send_file(context.chat_id, f"data{sep}everyday.jpg",
                                       caption=f"{data['content']}\n释义：{data['note']}")
        remove(f"data{sep}everyday.jpg")
        await context.delete()
    except Exception as e:
        await context.edit(f"获取失败\n{e}")
