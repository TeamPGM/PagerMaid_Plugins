from pagermaid.listener import listener

@listener(is_plugin=True, outgoing=True, ignore_edited=False)
async def ok_true(context):
    try:
        await context.delete()
    except:
        pass
