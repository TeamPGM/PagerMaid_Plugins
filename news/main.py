from pagermaid.dependence import client
from pagermaid.enums import Message
from pagermaid.listener import listener


@listener(command="news", description="每日新闻、历史上的今天、天天成语、慧语香风、诗歌天地")
async def news(context: Message):
    msg = context.arguments
    if not msg:
        await context.edit("获取中 . . .")
    try:
        data = await client.get("https://news.topurl.cn/api")
        data = data.json()["data"]
        text = "📮 每日新闻 📮\n"
        for idx, i in enumerate(data["newsList"]):
            text += f"{idx + 1}. [{i['title']}]({i['url']})\n"

        text += "\n🎬 历史上的今天 🎬\n"
        for i in data["historyList"]:
            text += f"{i['event']}\n"

        text += "\n🧩 天天成语 🧩\n"
        text += f"{data['phrase']['phrase']}     ----{data['phrase']['explain']}\n"

        text += "\n🎻 慧语香风 🎻\n"
        text += f"{data['sentence']['sentence']}     ----{data['sentence']['author']}\n"

        text += "\n🎑 诗歌天地 🎑\n"
        text += (
            f"{''.join(data['poem']['content'])}     "
            f"----《{data['poem']['title']}》{data['poem']['author']}"
        )
        await context.edit(text)
    except Exception as e:
        await context.edit(f"获取失败\n{e}")
