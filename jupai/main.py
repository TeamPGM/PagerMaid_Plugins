import urllib.parse
import httpx
from io import BytesIO

from pagermaid.listener import listener
from pagermaid.enums import Message
from pagermaid.utils import lang

ju_pai_api = "https://api.txqq.pro/api/zt.php"


@listener(command="jupai", description="生成举牌小人", parameters="[text/reply]")
async def ju_pai(message: Message):

    if message.arguments:
        text = message.raw_text.split(maxsplit=1)[1].strip()
    elif message.reply_to_msg_id:
        reply_msg = await message.client.get_messages(
            message.chat_id,
            ids=message.reply_to_msg_id
        )
        if reply_msg:
            text = reply_msg.text.strip() if reply_msg.text else ""
        else:
            text = ""
    else:
        text = ""

    if not text:
        return await message.edit(lang("arg_error"))

    try:
        safe_text = "".join(text.split())
        image_url = f"{ju_pai_api}?msg={urllib.parse.quote(text)}"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            img_data = BytesIO(resp.content)
            img_data.name = "jupai.png"

        await message.client.send_file(
            message.chat_id,
            file=img_data,
            reply_to=message.reply_to_msg_id,
            force_document=False,
        )
        await message.delete()

    except Exception as e:
        await message.edit(f"获取失败 ~ {e.__class__.__name__}")