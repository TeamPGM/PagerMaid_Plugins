from wordcloud import WordCloud
from io import BytesIO
from os.path import exists
from os import makedirs, sep, remove
from PIL import Image
from collections import defaultdict
from requests import get
from pagermaid import version
from pagermaid.utils import execute, alias_command, pip_install
from pagermaid.listener import listener

pip_install("jieba")

import jieba

punctuation = {33: ' ', 34: ' ', 35: ' ', 36: ' ', 37: ' ', 38: ' ', 39: ' ', 40: ' ', 41: ' ', 42: ' ', 43: ' ',
               44: ' ', 45: ' ', 46: ' ', 47: ' ', 58: ' ', 59: ' ', 60: ' ', 61: ' ', 62: ' ', 63: ' ', 64: ' ',
               91: ' ', 92: ' ', 93: ' ', 94: ' ', 95: ' ', 96: ' ', 123: ' ', 124: ' ', 125: ' ', 126: ' ',
               65311: ' ', 65292: ' ', 65281: ' ', 12304: ' ', 12305: ' ', 65288: ' ', 65289: ' ', 12289: ' ',
               12290: ' ', 65306: ' ', 65307: ' ', 8217: ' ', 8216: ' ', 8230: ' ', 65509: ' ', 183: ' '}


@listener(is_plugin=True, outgoing=True, command=alias_command("groupword"),
          description="拉取最新 500 条消息生成词云，回复图片可自定义背景图。（图片白色区域为不显示部分）",
          parameters="[任意内容启用AI分词]")
async def group_word(context):
    if not exists(f"plugins{sep}groupword"):
        makedirs(f"plugins{sep}groupword")
    # 自定义背景图
    reply = await context.get_reply_message()
    if reply and reply.photo:
        if exists(f"plugins{sep}groupword{sep}circle.jpg"):
            remove(f"plugins{sep}groupword{sep}circle.jpg")
        await context.client.download_media(reply, file=f"plugins{sep}groupword{sep}circle.jpg")
        return await context.edit("自定义背景图设置完成。")

    imported_1 = False
    if len(context.parameter) >= 1:
        pip_install("paddlepaddle-tiny", alias="paddle")
        imported_1 = True
    try:
        await context.edit('正在生成中。。。')
    except:
        return
    if not exists(f"plugins{sep}groupword{sep}wqy-microhei.ttc"):
        await context.edit('正在拉取中文字体文件。。。（等待时间请评估你的服务器）')
        r = get('https://cdn.jsdelivr.net/gh/anthonyfok/fonts-wqy-microhei/wqy-microhei.ttc')
        with open(f"plugins{sep}groupword{sep}wqy-microhei.ttc", "wb") as code:
            code.write(r.content)
    words = defaultdict(int)
    count = 0
    try:
        if imported_1:
            try:
                jieba.enable_paddle()
            except:
                imported_1 = False
        async for msg in context.client.iter_messages(context.chat, limit=500):
            if msg.id == context.id:
                continue
            if msg.text and not msg.text.startswith('/') and not msg.text.startswith('-') and not '//' in msg.text:
                try:
                    if imported_1:
                        for word in jieba.cut(msg.text.translate(punctuation), use_paddle=True):
                            word = word.lower()
                            words[word] += 1
                    else:
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
        if not exists(f"plugins{sep}groupword{sep}circle.jpg"):
            image = WordCloud(font_path=f"plugins{sep}groupword{sep}wqy-microhei.ttc", width=800,
                              height=400).generate_from_frequencies(
                words).to_image()
        else:
            import numpy as np
            background = Image.open(f"plugins{sep}groupword{sep}circle.jpg")
            graph = np.array(background)  # noqa

            image = WordCloud(font_path=f"plugins{sep}groupword{sep}wqy-microhei.ttc", width=800,
                              height=800,
                              mask=graph,
                              scale=5,
                              background_color='white').generate_from_frequencies(
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
