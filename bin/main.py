from json.decoder import JSONDecodeError

from pagermaid.enums import Message, AsyncClient
from pagermaid.listener import listener


@listener(command="bin", description="查询信用卡信息", parameters="[bin（4到8位数字）]")
async def card(request: AsyncClient, message: Message):
    await message.edit("正在查询中...")
    try:
        card_bin = int(message.arguments)
    except ValueError:
        await message.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    try:
        r = await request.get(f"https://data.handyapi.com/bin/{card_bin}")
    except:
        await message.edit("出错了呜呜呜 ~ 无法访问到 handyapi 。")
        return
    try:
        bin_json = r.json()
    except JSONDecodeError:
        await message.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    status = bin_json.get("Status")
    if status != "SUCCESS":
        await message.edit("出错了呜呜呜 ~ 无效的 bin 。")
        return

    msg_out = [f"BIN：{card_bin}"]
    try:
        msg_out.append("卡品牌：" + bin_json["Scheme"].lower())
    except (KeyError, TypeError):
        pass
    try:
        msg_out.append("卡类型：" + bin_json["Type"].lower())
    except (KeyError, TypeError):
        pass
    try:
        msg_out.append("卡种类：" + bin_json["CardTier"].lower())
    except (KeyError, TypeError):
        pass
    try:
        msg_out.append("发卡行：" + bin_json["Issuer"].lower())
    except (KeyError, TypeError):
        pass
    try:
        msg_out.append("发卡国家：" + bin_json["Country"]["Name"])
    except (KeyError, TypeError):
        pass
    await message.edit("\n".join(msg_out))
