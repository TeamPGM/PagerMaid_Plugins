""" Pagermaid autorespond plugin. """

from telethon.events import StopPropagation
from pagermaid import persistent_vars, log, version
from pagermaid.listener import listener
from pagermaid.utils import alias_command

persistent_vars.update({'autorespond': {'enabled': False, 'message': None, 'amount': 0}})


@listener(is_plugin=True, outgoing=True, command=alias_command("autorespond"),
          description="启用自动回复。",
          parameters="<message>")
async def autorespond(context):
    """ Enables the auto responder. """
    message = "我还在睡觉... ZzZzZzZzZZz"
    if context.arguments:
        message = context.arguments
    await context.edit("成功启用自动响应器。")
    await log(f"启用自动响应器，将自动回复 `{message}`.")
    persistent_vars.update({'autorespond': {'enabled': True, 'message': message, 'amount': 0}})
    raise StopPropagation


@listener(outgoing=True)
async def disable_responder(context):
    if persistent_vars['autorespond']['enabled']:
        await log(f"禁用自动响应器。 在闲置期间 {persistent_vars['autorespond']['amount']}"
                  f" 条消息被自动回复")
        persistent_vars.update({'autorespond': {'enabled': False, 'message': None, 'amount': 0}})


@listener(incoming=True)
async def private_autorespond(context):
    if persistent_vars['autorespond']['enabled']:
        if context.is_private and not (await context.get_sender()).bot:
            persistent_vars['autorespond']['amount'] += 1
            await context.reply(persistent_vars['autorespond']['message'])


@listener(incoming=True)
async def mention_autorespond(context):
    if persistent_vars['autorespond']['enabled']:
        try:
            if context.message.mentioned and not (await context.get_sender()).bot:
                persistent_vars['autorespond']['amount'] += 1
                await context.reply(persistent_vars['autorespond']['message'])
        except AttributeError:
            return
