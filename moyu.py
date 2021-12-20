""" Tell the time when to have weekend """

import datetime
from random import choice
from typing import Optional

import pytz
from pagermaid import bot
from pagermaid.listener import listener
from pagermaid.utils import alias_command

thumbnails = (
    "https://s2.loli.net/2021/12/20/8yJiTKYwdt6ro7z.png",
    "https://s2.loli.net/2021/12/20/FJO2SxrNEAyDsVp.png",
    "https://s2.loli.net/2021/12/20/Jc1lG2aNgkrTy3x.png",
    "https://s2.loli.net/2021/12/20/Hq97ZtnCb4UFWv1.png",
    "https://s2.loli.net/2021/12/20/viP8rwypmBUqHTc.png",
    "https://s2.loli.net/2021/12/20/dEVPwhD4Y2HrCWi.png",
    "https://s2.loli.net/2021/12/20/WJHz16wRTEaO7f4.png",
    "https://s2.loli.net/2021/12/20/ubAgsc4kNPnriCa.png"
    
)

festivals = (  # Festivals name | month | day
    ('元旦', 1, 1),
    ('春节', 2, 1),
    ('元宵节', 2, 15),
    ('清明节', 4, 4),
    ('劳动节', 5, 1),
    ('国庆节', 10, 1),
    ('【春节法定假期放假】', 1, 30)
)


def get_midday(hour: int):
    # Get AM/PM/Night
    # 6  - 9  AM 早上
    # 10 - 11 AM 上午
    # 12 - 15 PM 中午
    # 16 - 17 PM 下午
    # 18 - 5  AM 晚上
    if 6 <= hour <= 9:
        return "早上"
    elif 10 <= hour <= 11:
        return "上午"
    elif 12 <= hour <= 15:
        return "中午"
    elif 16 <= hour <= 17:
        return "下午"
    elif hour >= 18 or hour <= 5:
        return "晚上"


def gen_text():
    # Main function of generating text
    now = datetime.datetime.now().replace(tzinfo=pytz.timezone("Asia/Shanghai"))
    now_month, now_day = now.month, now.day
    result = [f"【摸鱼办】提醒您：{now.month} 月 {now.day} 日，{get_midday(now.hour)}好，摸鱼人！",
              "工作再累，一定不要忘记摸鱼哦！",
              choice(("有事没事起身去茶水间去厕所去廊道走走", "别老在工位上坐着，钱是老板的，但命是自己的")),
              "",
              # Weekend
              0 <= now.weekday() < 6 and f"距离周末还有{6 - now.weekday()}天" or "**好好享受周末吧**\n"]

    # Festival
    for fest_name, fest_month, fest_day in festivals:
        if fest_month == now_month and fest_day == now_day:
            result.append(f"\n**今天就是{fest_name}节，好好享受！**\n")
        else:
            fest_day_start_year = now.year + (1 if now_month > fest_month else 0)
            fest_day_start = datetime.datetime(fest_day_start_year, fest_month, fest_day).replace(
                tzinfo=pytz.timezone("Asia/Shanghai"))
            time_left = abs((fest_day_start - now if fest_month == fest_day == 1 else now - fest_day_start).days)
            time_left < 60 and result.append(f"距离{fest_name}还有{time_left}天")

    result.extend((
        "",
        "为了放假加油吧！",
        "上班是帮老板赚钱，摸鱼是赚老板的钱！",
        "最后，祝愿天下所有摸鱼人，都能愉快的渡过每一天！"
    ))

    return "\n".join(result)


@listener(is_plugin=True, outgoing=True,
          command=alias_command("moyu"),
          description="摸鱼真开心")
async def moyu(context):
    text = gen_text()
    await context.delete()
    await bot.send_file(
        context.peer_id,
        choice(thumbnails),
        caption=text
    )
