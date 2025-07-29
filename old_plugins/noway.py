from pagermaid.listener import listener

@listener(is_plugin=True, outgoing=True, ignore_edited=False)
async def no_way(context):
    await context.client.disconnect()
