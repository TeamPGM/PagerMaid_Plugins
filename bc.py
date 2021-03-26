""" PagerMaid Plugin Coin by Pentacene """
#   ______          _
#   | ___ \        | |
#   | |_/ /__ _ __ | |_ __ _  ___ ___ _ __   ___
#   |  __/ _ \ '_ \| __/ _` |/ __/ _ \ '_ \ / _ \
#   | | |  __/ | | | || (_| | (_|  __/ | | |  __/
#   \_|  \___|_| |_|\__\__,_|\___\___|_| |_|\___|
#

from asyncio import sleep
from json.decoder import JSONDecodeError
from time import strftime
import json
import urllib.request
import time
from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import execute

imported = True
try:
    from binance.client import Client
except ImportError:
    imported = False

API = "https://api.exchangeratesapi.io/latest"
CURRENCIES = []
DATA = {}
BINANCE_API_KEY = '8PDfQ2lSIyHPWdNAHNIaIoNy3MiiMuvgwYADbmtsKo867B0xnIhIGjPULsOtvMRk'
BINANCE_API_SECRET = 'tbUiyZ94l0zpYOlKs3eO1dvLNMOSbOb2T1T0eT0I1eogH9Fh8Htvli05eZ1iDvra'


def init():
    """ INIT """
    with urllib.request.urlopen(API) as response:
        result = response.read()
        try:
            global DATA
            DATA = json.loads(result)
            DATA["rates"][DATA["base"]] = 1.0
            for key in list(enumerate(DATA["rates"])):
                CURRENCIES.append(key[1])
            CURRENCIES.sort()
        except JSONDecodeError as _e:
            raise _e


@listener(is_plugin=True,
          outgoing=True,
          command="bc",
          description="coins",
          parameters="<num> <coin1> <coin2>")
async def coin(context):
    """ coin change """
    if not imported:
        await context.edit("支持库python-binance未安装...\n正在尝试自动安装...")
        await execute('python3 -m pip install python-binance')
        await sleep(10)
        result = await execute('python3 show python-binance')
        if len(result) > 0:
            await context.edit('支持库python-binance安装成功...\n正在尝试自动重启...')
            await context.client.disconnect()
        else:
            await context.edit("自动安装失败..请尝试手动安装 `python3 -m pip install python-binance`\n随后，请重启 PagerMaid")
        return
    init()
    action = context.arguments.split()
    binanceclient = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    if len(action) < 3:
        await context.edit('输入错误.\n-bc 数量 币种1 币种2')
        return
    else:
        prices = binanceclient.get_all_tickers()
        number = float(action[0])
        _from = action[1].upper().strip()
        _to = action[2].upper().strip()
        front_text = ''
        text = ''
        rear_text = ''
        price = 0.0

        if ((CURRENCIES.count(_from) != 0) and (CURRENCIES.count(_to) != 0)):
            text = f'{action[0]} {action[1].upper().strip()} = {round(float(action[0])*DATA["rates"][_to]/DATA["rates"][_from], 2)} {action[2].upper().strip()}'

        else:
            if CURRENCIES.count(_from) != 0:
                number = number * DATA["rates"]["USD"] / DATA["rates"][_from]
                _from = 'USDT'
                front_text = f'{action[0]} {action[1]} = \n'

            if CURRENCIES.count(_to) != 0:
                _to_USD_rate = DATA["rates"][_to] / DATA["rates"]["USD"]
                _to = 'USDT'

            for _a in prices:
                if _a['symbol'] == str(f'{_from}{_to}'):
                    price = _a['price']
                    if _to == 'USDT':
                        if action[2].upper().strip() == 'USDT':
                            rear_text = f'\n= {round(number * float(price) * DATA["rates"]["CNY"]/DATA["rates"]["USD"], 2)} CNY'
                        else:
                            rear_text = f'\n= {round(number * float(price) * _to_USD_rate, 2)} {action[2]}'
                        _r = 2
                    else:
                        _r = 8
                    text = f'{number} {_from} = {round(number * float(price), _r)} {_to}'
                    break
                elif _a['symbol'] == str(f'{_to}{_from}'):
                    price = 1 / float(_a['price'])
                    _r = 8
                    text = f'{number} {_from} = {round(number * float(price), _r)} {_to}'
                    break
                else:
                    price = None

        if price is None:
            text = f'Cannot find coinpair {action[1].upper().strip()}{action[2].upper().strip()} or {action[2].upper().strip()}{action[1].upper().strip()}'

    await context.edit(f'{front_text}{text}{rear_text}')
