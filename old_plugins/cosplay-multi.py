from random import randint, random
from requests import get
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from os import remove


@listener(is_plugin=True, outgoing=True, command=alias_command("cosm"),
          description="多网站随机获取cosplay图片，会自动重试哦")
async def cosm(context):
    await context.edit("获取中 . . .")
    status = False
    for _ in range(20):  # 最多重试20次
        website = randint(0, 6)
        filename = "cosm" + str(random())[2:] + ".png"
        try:
            if website == 0:
                img = get("https://api.helloworld.la/xiezhen_cosplay.php")
            elif website == 1:
                img = get("https://api.vvhan.com/api/mobil.girl?type=json")
            elif website == 2:
                img = get("https://api.helloworld.la/xiezhen_weimei.php")
            elif website == 3:
                img = get("http://api.rosysun.cn/cos")
            elif website == 4:
                img = get("https://uploadbeta.com/api/pictures/random/?key=%E5%8A%A8%E6%BC%AB")
            elif website == 5:
                img = get("https://uploadbeta.com/api/pictures/random/?key=%E4%BA%8C%E6%AC%A1%E5%85%83")
            else:
                img = get("https://xn--wcs142h.herokuapp.com/")
            if img.status_code == 200:
                if website == 3:
                    img = get(img.content)
                    if img.status_code != 200:
                        continue  # 再试一次
                with open(filename, 'wb') as f:
                    f.write(img.content)
                await context.edit("上传中 . . .")
                await context.client.send_file(context.chat_id, filename)
                status = True
                break  # 成功了就赶紧结束啦！
        except:
            try:
                remove(filename)
            except:
                pass
            continue
    try:
        remove(filename)
    except:
        pass
    try:
        await context.delete()
    except:
        pass
    if not status:
        try:
            remove(filename)
        except:
            pass
        try:
            await context.delete()
        except:
            pass
        await context.client.send_message(context.chat_id, "出错了呜呜呜 ~ 试了好多好多次都无法访问到服务器 。")
