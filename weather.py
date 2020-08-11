import json
from requests import get
from pagermaid.listener import listener
from pagermaid.utils import obtain_message

icons = {
    "01d": "🌞",
    "01n": "🌚",
    "02d": "⛅️",
    "02n": "⛅️",
    "03d": "☁️",
    "03n": "☁️",
    "04d": "☁️",
    "04n": "☁️",
    "09d": "🌧",
    "09n": "🌧",
    "10d": "🌦",
    "10n": "🌦",
    "11d": "🌩",
    "11n": "🌩",
    "13d": "🌨",
    "13n": "🌨",
    "50d": "🌫",
    "50n": "🌫",
}

@listener(is_plugin=True, outgoing=True, command="weather",
          description="查询天气",
          parameters="<城市>")
async def weather(context):
    await context.edit("获取中 . . .")
    try:
        message = await obtain_message(context)
    except ValueError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    req = get("http://api.openweathermap.org/data/2.5/weather?appid=973e8a21e358ee9d30b47528b43a8746&units=metric&lang=zh_cn&q=" + message)
    if req.status_code == 200:
        data = json.loads(req.text)
        cityName = "{}, {}".format(data["name"], data["sys"]["country"])
        tempInC = round(data["main"]["temp"], 2)
        tempInF = round((1.8 * tempInC) + 32, 2)
        icon = data["weather"][0]["icon"]
        desc = data["weather"][0]["description"]
        res = "{}\n🌡{}℃ ({}F)\n{} {}".format(
            cityName, tempInC, tempInF, icons[icon], desc
        )
        await context.edit(res)
    else:
        await context.edit("出错了呜呜呜 ~ 无法访问到 openweathermap.org 。")