from pagermaid.dependence import client
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils.bot_utils import edit_delete


@listener(command="diss", description="儒雅随和版祖安语录。")
async def diss(message: Message):
    for _ in range(5):
        req = await client.get("https://api.oddfar.com/yl/q.php?c=1009&encode=text")
        if req.status_code == 200:
            return await message.edit(req.text)
    await edit_delete(message, "出错了呜呜呜 ~ 试了好多好多次都无法访问到 API 服务器 。")
