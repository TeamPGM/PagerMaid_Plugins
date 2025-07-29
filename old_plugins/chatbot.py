import json
import requests
from urllib.parse import quote
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command, obtain_message, lang, clear_emojis


@listener(is_plugin=True, outgoing=True, command=alias_command("chatbot"),
          description="使用自然语言处理 (NLP) 来帮助用户通过文本进行交互。（支持回复）",
          parameters="<字符串>")
async def chatbot(context):
    try:
        text = await obtain_message(context)
    except ValueError:
        await context.edit(lang('msg_ValueError'))
        return
    text = clear_emojis(text)
    text = quote(text)

    try:
        req_data = requests.get(f"https://api.affiliateplus.xyz/api/chatbot?message={text}"
                                f"&botname=pagermaid&ownername=xtao-labs&user=20")
    except Exception as e:
        await context.edit('出错了呜呜呜 ~ 无法访问 API ')
        return
    if not req_data.status_code == 200:
        return await context.edit('出错了呜呜呜 ~ 无法访问 API ')

    try:
        req_data = json.loads(req_data.text)
        req_data = req_data["message"]
    except Exception as e:
        await context.edit("出错了呜呜呜 ~ 解析JSON时发生了错误。")
        return

    await context.edit(req_data)
