""" Module to automate message deletion. """
from asyncio import sleep
from pagermaid import log
from pagermaid.listener import listener
from pagermaid.utils import alias_command, lang


@listener(is_plugin=False, outgoing=True, command=alias_command("dme"),
          description=lang('sp_des'),
          parameters=lang('sp_parameters'))
async def selfprune(context):
    """ Deletes specific amount of messages you sent. """
    msgs = []
    count_buffer = 0
    if not len(context.parameter) == 1:
        if not context.reply_to_msg_id:
            await context.edit(lang('arg_error'))
            return
        async for msg in context.client.iter_messages(
                context.chat_id,
                from_user="me",
                min_id=context.reply_to_msg_id,
        ):
            msgs.append(msg)
            count_buffer += 1
            if len(msgs) == 100:
                await context.client.delete_messages(context.chat_id, msgs)
                msgs = []
        if msgs:
            await context.client.delete_messages(context.chat_id, msgs)
        if count_buffer == 0:
            await context.delete()
            count_buffer += 1
        await log(f"{lang('prune_hint1')}{lang('sp_hint')} {str(count_buffer)} {lang('prune_hint2')}")
        notification = await send_prune_notify(context, count_buffer, count_buffer)
        await sleep(1)
        await notification.delete()
        return
    try:
        count = int(context.parameter[0])
        await context.delete()
    except ValueError:
        await context.edit(lang('arg_error'))
        return
    async for message in context.client.iter_messages(context.chat_id, from_user="me"):
        if count_buffer == count:
            break
        msgs.append(message)
        count_buffer += 1
        if len(msgs) == 100:
            await context.client.delete_messages(context.chat_id, msgs)
            msgs = []
    if msgs:
        await context.client.delete_messages(context.chat_id, msgs)
    await log(f"{lang('prune_hint1')}{lang('sp_hint')} {str(count_buffer)} / {str(count)} {lang('prune_hint2')}")
    try:
        notification = await send_prune_notify(context, count_buffer, count)
        await sleep(1)
        await notification.delete()
    except ValueError:
        pass


async def send_prune_notify(context, count_buffer, count):
    return await context.client.send_message(
        context.chat_id,
        lang('spn_deleted')
        + str(count_buffer) + " / " + str(count)
        + lang('prune_hint2')
    )
