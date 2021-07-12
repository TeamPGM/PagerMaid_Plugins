import json, requests
from pagermaid.listener import listener
from pagermaid.utils import obtain_message, alias_command

@listener(is_plugin=True, outgoing=True, command=alias_command("bin"), 
          description="查询信用卡信息", 
          parameters="<bin（4到8位数字）>")
async def card(context):
    await context.edit('正在查询中...')
    try:
        card_bin = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    try:
        r = requests.get("https://lookup.binlist.net/" + card_bin)
    except:
        await context.edit("出错了呜呜呜 ~ 无法访问到binlist。")
        return
    if r.status_code == 404:
        await context.edit("出错了呜呜呜 ~ 目标卡头不存在")
        return
    if r.status_code == 429:
        await context.edit("出错了呜呜呜 ~ 每分钟限额超过，请等待一分钟再试")
        return
    
    bin_json = json.loads(r.content.decode("utf-8"))

    msg_out = []
    msg_out.extend(["BIN：" + card_bin])
    try:
        msg_out.extend(["卡品牌：" + bin_json['scheme']])
    except KeyError:
        pass
    try:
        msg_out.extend(["卡类型：" + bin_json['type']])
    except KeyError:
        pass
    try:
        msg_out.extend(["卡种类：" + bin_json['brand']])
    except KeyError:
        pass
    try:
        msg_out.extend(["发卡行：" + bin_json['bank']["name"]])
    except KeyError:
        pass
    try:
        if bin_json['prepaid']:
            msg_out.extend(["是否预付：是"])
        else:
            msg_out.extend(["是否预付：否"])
    except KeyError:
        pass
    try:
        msg_out.extend(["发卡国家：" + bin_json['country']['name']])
    except KeyError:
        pass
    await context.edit("\n".join(msg_out))
