from pagermaid import redis, redis_status, log, version
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, outgoing=True, command=alias_command("repeat"),
          description='自动复读（无引用）一个人的消息。',
          parameters="<[reply]|status>")
async def repeat(context):
    if not context.is_group:
        await context.edit('请在群组中运行。')
        return
    if not redis_status():
        await context.edit('出错了呜呜呜 ~ Redis 数据库离线。')
        return
    reply = await context.get_reply_message()
    if not reply or not reply.sender:
        await context.edit('请回复一个用户。')
        return
    uid = reply.sender_id
    if len(context.parameter) == 1:
        if redis.get(f'repeat_{context.chat_id}_{uid}'):
            await context.edit('此用户存在于自动复读列表。')
        else:
            await context.edit('此用户不存在于自动复读列表。')
        return
    if redis.get(f'repeat_{context.chat_id}_{uid}'):
        redis.delete(f'repeat_{context.chat_id}_{uid}')
        await context.edit('从自动复读列表移除成功。')
    else:
        redis.set(f'repeat_{context.chat_id}_{uid}', 'true')
        await context.edit('添加到自动复读列表成功。')


@listener(is_plugin=True, incoming=True, ignore_edited=True)
async def repeat_msg(context):
    """ Event handler. """
    if not redis_status():
        return
    if redis.get(f'repeat_{context.chat_id}_{context.sender_id}'):
        try:
            msg = await context.client.get_messages(context.chat_id, ids=context.id)
            return await context.client.send_message(context.chat_id, msg)
        except Exception as e:
            await log(f'Repeat Error:\n{e}')
