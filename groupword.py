from asyncio import sleep
from wordcloud import WordCloud
from io import BytesIO
from os.path import exists
from os import makedirs
from collections import defaultdict
from requests import get
from pagermaid.utils import execute, alias_command
from pagermaid.listener import listener

imported = True
punctuation = {33: ' ', 34: ' ', 35: ' ', 36: ' ', 37: ' ', 38: ' ', 39: ' ', 40: ' ', 41: ' ', 42: ' ', 43: ' ',
               44: ' ', 45: ' ', 46: ' ', 47: ' ', 58: ' ', 59: ' ', 60: ' ', 61: ' ', 62: ' ', 63: ' ', 64: ' ',
               91: ' ', 92: ' ', 93: ' ', 94: ' ', 95: ' ', 96: ' ', 123: ' ', 124: ' ', 125: ' ', 126: ' ',
               65311: ' ', 65292: ' ', 65281: ' ', 12304: ' ', 12305: ' ', 65288: ' ', 65289: ' ', 12289: ' ',
               12290: ' ', 65306: ' ', 65307: ' ', 8217: ' ', 8216: ' ', 8230: ' ', 65509: ' ', 183: ' '}
try:
    import jieba
except ImportError:
    imported = False


@listener(is_plugin=True, outgoing=True, command=alias_command("groupword"),
          description="拉取最新 300 条消息生成词云。")
async def group_word(context):
    if not imported:
        try:
            await context.edit("支持库 `jieba` 未安装...\n正在尝试自动安装...")
            await execute('python3 -m pip install jieba')
            await sleep(10)
            result = await execute('python3 show jieba')
            if len(result) > 0:
                await context.edit('支持库 `jieba` 安装成功...\n正在尝试自动重启...')
                await context.client.disconnect()
            else:
                await context.edit("自动安装失败..请尝试手动安装 `python3 -m pip install jieba` 随后，请重启 PagerMaid-Modify 。")
                return
        except:
            return
    try:
        await context.edit('正在生成中。。。')
    except:
        return
    if not exists("plugins/groupword"):
        makedirs("plugins/groupword")
    if not exists("plugins/groupword/wqy-microhei.ttc"):
        await context.edit('正在拉取中文字体文件。。。（等待时间请评估你的服务器）')
        r = get('https://cdn.jsdelivr.net/gh/anthonyfok/fonts-wqy-microhei/wqy-microhei.ttc')
        with open("plugins/groupword/wqy-microhei.ttc", "wb") as code:
            code.write(r.content)
    words = defaultdict(int)
    count = 0
    try:
        async for msg in context.client.iter_messages(context.chat, limit=500):
            if msg.id == context.id:
                continue
            if msg.text:
                try:
                    for word in jieba.cut(msg.text.translate(punctuation)):
                        word = word.lower()
                        words[word] += 1
                    count += 1
                except:
                    pass
    except:
        if count == 0:
            try:
                await context.edit('您已被 TG 官方限制。')
                return
            except:
                return
    try:
        image = WordCloud(font_path="plugins/groupword/wqy-microhei.ttc", width=800, height=400).generate_from_frequencies(
            words).to_image()
        stream = BytesIO()
        image.save(stream, 'PNG')
    except:
        await context.edit('词云生成失败。')
        return
    try:
        await context.client.send_message(context.chat, f'对最近的 {count} 条消息进行了分析。', file=stream.getvalue())
        await context.delete()
    except:
        return
