from telethon.tl.functions.channels import GetAdminedPublicChannelsRequest

from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=False, outgoing=True, command=alias_command("listusernames"),
          description='列出所有属于自己的公开群组/频道。',
          parameters="")
async def listusernames(context: "Message"):
    """ Get a list of your reserved usernames. """
    await context.edit('正在获取中...')
    result = await context.client(GetAdminedPublicChannelsRequest())
    output = "以下是属于我的所有公开群组/频道：\n\n"
    for i in result.chats:
        output += f"{i.title}\n@{i.username}\n\n"
    await context.edit(output)
