""" 查询食物嘌呤含量 """

# By tg @lowking0415
# extra requirements: bs4

imported = True

try:
    from bs4 import BeautifulSoup
except ImportError:
    imported = False

from asyncio import sleep
from requests import get
from pagermaid.listener import listener
from urllib import parse

@listener(is_plugin=True, outgoing=True, command="pl",
    description="输入【-pl 食物名】查询食物嘌呤含量",
    parameters="<食物名>")
async def pl(context):
    if not imported:
        await context.edit("请先安装依赖：\n`python3 -m pip install bs4`\n随后，请重启 pagermaid。")
        return
    action = context.arguments.split()
    if len(action) == 1:
        await context.edit("查询中 . . .")
        status = False

        st = action[0]
        st = st.encode('gb2312')
        m = {'tj_so':st,}
        s = parse.urlencode(m)
        for _ in range(3):  # 最多重试3次
            try:
                plhtml = get(f"http://www.gd2063.com/pl/?{s}")
                htmlStr = plhtml.content.decode("gbk")
                soup = BeautifulSoup(htmlStr, 'html.parser')
                arr = soup.find_all(name='a', attrs={"class": "heise"}, limit=10)
                result = ""
                for a in arr:
                    if (a.text != None):
                        txt = a.text.replace("嘌呤含量", "➟ ")
                        result = f"{result}{txt}\n"
                status = True
                await context.edit(result)
                break
            except:
                pass

        if not status:
            await context.edit(f"呜呜呜，试了3次都没查到呢")
    else:
        await context.edit(f"乱写什么东西呀！格式如下：\n"
                           f"【-pl 食物名】查询食物嘌呤含量")
        
    try:
        if not status:
            await sleep(2)
        else:
            await sleep(10)
        await context.delete()
    except:
        pass
