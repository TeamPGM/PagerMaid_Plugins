from pagermaid.dependence import client
from pagermaid.enums import Message
from pagermaid.listener import listener


@listener(command="whois", description="查看域名是否已被注册、注册日期、过期日期、域名状态、DNS解析服务器等。")
async def whois(context: Message):
    try:
        message = context.arguments
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    req = await client.get(f"https://namebeta.com/api/search/check?query={message}")

    if req.status_code == 200:
        try:
            data = (
                req.json()["whois"]["whois"].split("For more information")[0].rstrip()
            )
            new_data = []
            for i in data.split("\n"):
                if i.strip().startswith(">>> Last update"):
                    last_line = i.strip().replace(">>>", "").replace("<<<", "").strip()
                    new_data.append(f"\n<i>{last_line}</i>")
                elif ":" in i:
                    parts = i.split(":", 1)
                    new_data.append(f"<b>{parts[0]}:</b> <code>{parts[1].strip()}</code>")
                else:
                    if i.strip():
                        new_data.append(i)
            formatted_data = "\n".join(new_data)
        except:
            await context.edit("出错了呜呜呜 ~ 可能是域名不正确。")
            return
        await context.edit(
            f"<b>Whois for <code>{message}</code></b>\n\n"
            f"{formatted_data}",
            parse_mode="html",
        )
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 API 服务器 。")
