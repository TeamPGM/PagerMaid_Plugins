from pagermaid.listener import listener

jieba_imported = True

try:
    import jieba
except ImportError:
    jieba_imported = False


@listener(is_plugin=True, outgoing=True, ignore_edited=True)
async def kongge(context):
    if jieba_imported and context.text:
        seg_list = jieba.cut(context.text)
        seg_txt = ' '.join(seg_list)
        if not seg_txt == context.text:
            await context.edit(seg_txt)
