from pagermaid.listener import listener
from pagermaid import version

jieba_imported = True

try:
    import jieba
except ImportError:
    jieba_imported = False


@listener(is_plugin=True, outgoing=True, ignore_edited=True)
async def kongge(context):
    try:
        if jieba_imported and context.text and not context.via_bot and not context.forward:
            if context.text.startswith('-') or context.text.startswith('/'):
                return
            seg_list = jieba.cut(context.text)
            seg_txt = ' '.join(seg_list)
            seg_txt.replace('@ ', '@')
            if not seg_txt == context.text:
                await context.edit(seg_txt)
    except:
        pass
