""" Pagermaid currency exchange rates plugin. Plugin by @fruitymelon """

import asyncio, json
from json.decoder import JSONDecodeError
import urllib.request
from pagermaid.listener import listener

API = "https://api.exchangeratesapi.io/latest"
currencies = []
data = {}

inited = False


def init():
    with urllib.request.urlopen(API) as response:
        result = response.read()
        try:
            global data
            data = json.loads(result)
            data["rates"][data["base"]] = 1.0
            for key in list(enumerate(data["rates"])):
                currencies.append(key[1])
            currencies.sort()
        except JSONDecodeError as e:
            raise e
        global inited
        inited = True


init()


@listener(is_plugin=True, outgoing=True, command="rate",
          description="Currency exchange rate plugin.",
          parameters="<FROM> <TO>")
async def rate(context):
    while not inited:
        await asyncio.sleep(1)
    if not context.parameter:
        await context.edit(
            f"This is the currency exchange rate plugin.\n\nUsage: `-rate <FROM> <TO>`\n\nAvailable currencies: {', '.join(currencies)}")
        return
    if len(context.parameter) != 2:
        await context.edit(f"Usage: `-rate <FROM> <TO>`\n\n`{', '.join(currencies)}`")
        return
    FROM = context.parameter[0].upper().strip()
    TO = context.parameter[1].upper().strip()
    if currencies.count(FROM) == 0:
        await context.edit(
            f"Currency type {FROM} is not supported. Choose one among `{', '.join(currencies)}` instead.")
        return
    if currencies.count(TO) == 0:
        await context.edit(f"Currency type {TO} is not supported. Choose one among `{', '.join(currencies)}` instead.")
        return
    await context.edit(f'{FROM} : {TO} = 1 : {int(10000*data["rates"][TO]/data["rates"][FROM])/10000}')
