""" 查询食物嘌呤含量 """

# By tg @lowking0415
# extra requirements: bs4
from asyncio import sleep
from requests import get
from sys import executable
from pagermaid.listener import listener
from pagermaid.utils import alias_command, pip_install

pip_install("bs4")

from bs4 import BeautifulSoup
from urllib import parse


@listener(is_plugin=True, outgoing=True, command=alias_command("pl"),
          description="输入【-pl 食物名】查询食物嘌呤含量",
          parameters="<食物名>")
async def pl(context):
    action = context.arguments.split()
    status = False
    if len(action) == 1:
        await context.edit("查询中 . . .")

        st = action[0]
        st = st.encode('gb2312')
        m = {'tj_so': st, }
        s = parse.urlencode(m)
        for _ in range(2):  # 最多重试2次
            try:
                try:
                    plhtml = get(f"http://www.gd2063.com/pl/?{s}", timeout=5)
                except:
                    await context.edit("api请求异常，请访问\nhttp://www.gd2063.com/\n查看是否正常")
                    status = True
                    break
                htmlStr = plhtml.content.decode("gbk")
                soup = BeautifulSoup(htmlStr, 'html.parser')
                arr = soup.find_all(name='a', attrs={"class": "heise"}, limit=10)
                result = ""
                for a in arr:
                    if a.text is not None and a.text != "":
                        txt = a.text.replace("嘌呤含量", "➟ ")
                        result = f"{result}{txt}\n"
                if result == "":
                    await context.edit("没有查到结果")
                else:
                    await context.edit(result)
                status = True
                break
            except:
                await sleep(5)
                pass

        if not status:
            await context.edit(f"呜呜呜，试了2次都没查到呢")
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
