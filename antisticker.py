""" Auto-delete sticker when someone reply """

from pagermaid import user_id
from pagermaid.listener import listener


@listener(incoming=True, ignore_edited=True)
async def auto_remove_sticker(context):
    """ Event handler to remove stickers. """
    try:
        reply = await context.get_reply_message()
    except:
        return
    if reply:
        if reply.sender:
            reply_user_id = reply.sender.id
        else:
            return
        if context.sticker:
            return
        if not reply.sticker:
            return
        if context.chat_id > 0:
            return
        if context.sender:
            try:
                if context.sender.bot:
                    return
            except AttributeError:
                pass
    else:
        return

    if reply_user_id == user_id:
        try:
            await reply.delete()
        except:
            pass
