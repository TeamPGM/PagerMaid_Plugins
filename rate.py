""" Pagermaid currency exchange rates plugin. Plugin by @fruitymelon and @xtaodada """

import sys
import urllib.request
from pagermaid.listener import listener, config

# i18n 
## 默认语言
lang_rate = {"des": "货币汇率插件", "arg": "<FROM> <TO> <NUM>", "not": "请先安装依赖：`python3 -m pip install xmltodict`\n随后，请重启 pagermaid。", "help": "这是货币汇率插件\n\n使用方法: `-rate <FROM> <TO> <NB>`\n\n支持货币: \n", "nc": "不是支持的货币. \n\n支持货币: \n"}
## 其他语言
if config["application_language"] == "en":
    lang_rate = {"des": "Currency exchange rate plugin", "arg": "<FROM> <TO> <NUM>", "not": "Please run: `python3 -m pip install xmltodict`\nand restart pagermaid。", "help": "Currency exchange rate plugin\n\nUsage: `-rate <FROM> <TO> <NB>`\n\nSupport: \n", "nc": "is not support\n\nSupport: \n"}

imported = True
API = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
currencies = []
rates = {}


def init():
    with urllib.request.urlopen(API) as response:
        result = response.read()
        try:
            global rate_data, rates
            rate_data = xmltodict.parse(result)
            rate_data = rate_data['gesmes:Envelope']['Cube']['Cube']['Cube']
            for i in rate_data:
                currencies.append(i['@currency'])
                rates[i['@currency']] = float(i['@rate'])
            currencies.sort()
        except Exception as e:
            raise e


try:
    import xmltodict

    init()
except ImportError:
    imported = False


def logsync(message):
    sys.stdout.writelines(f"{message}\n")


@listener(is_plugin=True, outgoing=True, command="rate",
          description=lang_rate["des"],
          parameters=lang_rate["arg"])
async def rate(context):
    if not imported:
        await context.edit(lang_rate["not"])
        return
    if not context.parameter:
        await context.edit(
            f"{lang_rate['help']}{', '.join(currencies)}")
        return
    if len(context.parameter) != 3:
        await context.edit(f"{lang_rate['help']}{', '.join(currencies)}")
        return
    FROM = context.parameter[0].upper().strip()
    TO = context.parameter[1].upper().strip()
    try:
        NB = float(context.parameter[2].strip())
    except:
        NB = 1.0
    if currencies.count(FROM) == 0:
        await context.edit(
            f"{FROM}{lang_rate['nc']}{', '.join(currencies)}")
        return
    if currencies.count(TO) == 0:
        await context.edit(f"{TO}{lang_rate['nc']}{', '.join(currencies)}")
        return
    rate_num = round(rates[TO] / rates[FROM] * NB, 2)
    await context.edit(f'{FROM} : {TO} = {NB} : {rate_num}')
