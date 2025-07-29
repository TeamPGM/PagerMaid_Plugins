""" Pagermaid Plugins Fuck """
#   ______          _
#   | ___ \        | |
#   | |_/ /__ _ __ | |_ __ _  ___ ___ _ __   ___
#   |  __/ _ \ '_ \| __/ _` |/ __/ _ \ '_ \ / _ \
#   | | |  __/ | | | || (_| | (_|  __/ | | |  __/
#   \_|  \___|_| |_|\__\__,_|\___\___|_| |_|\___|
#

from datetime import timedelta
from telethon.tl.types import ChannelParticipantsAdmins
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, incoming=True, outgoing=True, command=alias_command("fuck"),
          description="回复你要踢出的人或-fuck <TelegramID>")
async def fuck(context):
    """ kick and ban this member """
    reply = await context.get_reply_message()
    if context.is_group:
        if reply:
            if reply.sender:
                try:
                    if reply.sender.last_name is None:
                        reply_last_name = ''
                    else:
                        reply_last_name = reply.sender.last_name
                except AttributeError:
                    try:
                        await context.edit('无法获取所回复的用户。')
                    except:
                        pass
                    return
            else:
                try:
                    await context.edit('无法获取所回复的用户。')
                except:
                    pass
                return
            if context.sender:
                try:
                    if context.sender.last_name is None:
                        context_last_name = ''
                    else:
                        context_last_name = context.sender.last_name
                except AttributeError:
                    try:
                        await context.edit('无法获取所回复的用户。')
                    except:
                        pass
                    return
            else:
                try:
                    await context.edit('无法获取所回复的用户。')
                except:
                    pass
                return
            admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
            if context.sender in admins:
                try:
                    await context.client.edit_permissions(context.chat_id, reply.sender.id, view_messages=False)
                    await context.client.send_message(
                        context.chat_id,
                        f'[{reply.sender.first_name}{reply_last_name}](tg://user?id={reply.sender.id}) 已被踢出群聊',
                        reply_to=reply.id
                    )
                    await context.delete()
                except:
                    pass
            else:
                try:
                    await context.client.edit_permissions(context.chat_id, context.sender.id, timedelta(seconds=60),
                                                          send_messages=False, send_media=False, send_stickers=False,
                                                          send_gifs=False, send_games=False, send_inline=False,
                                                          send_polls=False, invite_users=False, change_info=False,
                                                          pin_messages=False)
                    await context.client.send_message(
                        context.chat_id,
                        f'[{context.sender.first_name}{context_last_name}](tg://user?id={context.sender.id}) '
                        f'由于乱玩管理员命令 已被禁言60秒',
                        reply_to=context.id
                    )
                    await context.delete()
                except:
                    pass
        else:
            if context.arguments == '':
                return
            else:
                try:
                    userid = int(context.arguments)
                    if userid < 0:
                        return await context.edit('输入值错误。')
                except ValueError:
                    await context.edit('输入值错误。')
                    return
                admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
                if context.sender in admins:
                    try:
                        await context.client.edit_permissions(context.chat_id, userid, view_messages=False)
                        await context.client.send_message(
                            context.chat_id,
                            f'[{userid}](tg://user?id={userid}) 已被踢出群聊',
                            reply_to=context.id
                        )
                        await context.delete()
                    except:
                        pass
                else:
                    try:
                        await context.client.edit_permissions(context.chat_id, context.sender.id, timedelta(seconds=60),
                                                              send_messages=False, send_media=False,
                                                              send_stickers=False, send_gifs=False, send_games=False,
                                                              send_inline=False, send_polls=False, invite_users=False,
                                                              change_info=False, pin_messages=False)
                        await context.client.send_message(
                            context.chat_id,
                            f'[{context.sender.first_name}{context.sender.last_name}](tg://user?id={context.sender.id}) '
                            f'由于乱玩管理员命令 已被禁言60秒',
                            reply_to=context.id
                        )
                        await context.delete()
                    except:
                        pass

    else:
        pass
