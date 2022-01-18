""" Module to automate message deletion. """
import random
from asyncio import sleep
from datetime import datetime, timedelta, timezone
from telethon.tl.functions.account import UpdateProfileRequest
from emoji import emojize
from pagermaid import bot, log, version
from pagermaid.listener import listener

auto_change_name_init = False
dizzy = emojize(":dizzy:", use_aliases=True)
cake = emojize(":cake:", use_aliases=True)
all_time_emoji_name = ["clock12", "clock1230", "clock1", "clock130", "clock2", "clock230", "clock3", "clock330",
                       "clock4", "clock430", "clock5", "clock530", "clock6", "clock630", "clock7", "clock730", "clock8",
                       "clock830", "clock9", "clock930", "clock10", "clock1030", "clock11", "clock1130"]
time_emoji_symb = [emojize(":%s:" % s, use_aliases=True) for s in all_time_emoji_name]


@listener(incoming=True, outgoing=True, ignore_edited=True)
async def change_name_auto(context):
    global auto_change_name_init
    if auto_change_name_init:
        return
    else:
        auto_change_name_init = True
    await log("开始每 30 秒更新一次 last_name")
    while True:
        try:
            time_cur = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(timezone(
                timedelta(hours=8))).strftime('%H:%M:%S:%p:%a')
            hour, minu, seco, p, abbwn = time_cur.split(':')
            if seco == '00' or seco == '30':
                shift = 0
                if int(minu) > 30: shift = 1
                hsym = time_emoji_symb[(int(hour) % 12) * 2 + shift]
                for_fun = random.random()
                if for_fun < 0.10:
                    last_name = '%s时%s分 %s' % (hour, minu, hsym)
                elif for_fun < 0.30:
                    last_name = '%s:%s %s %s %s' % (hour, minu, p, abbwn, hsym)
                elif for_fun < 0.60:
                    last_name = '%s:%s %s UTC+8 %s' % (hour, minu, p, hsym)
                elif for_fun < 0.90:
                    last_name = '%s' % dizzy
                else:
                    last_name = '%s' % cake
                await bot(UpdateProfileRequest(last_name=last_name))
        except:
            pass
        await sleep(1)
