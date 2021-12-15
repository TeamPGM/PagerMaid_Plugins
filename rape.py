""" Pagermaid Plugins Rape """
#   ______          _
#   | ___ \        | |
#   | |_/ /__ _ __ | |_ __ _  ___ ___ _ __   ___
#   |  __/ _ \ '_ \| __/ _` |/ __/ _ \ '_ \ / _ \
#   | | |  __/ | | | || (_| | (_|  __/ | | |  __/
#   \_|  \___|_| |_|\__\__,_|\___\___|_| |_|\___|
#

from datetime import timedelta
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.errors.rpcerrorlist import ChatAdminRequiredError
from pagermaid.listener import listener
from pagermaid.utils import alias_command


@listener(is_plugin=True, incoming=True, outgoing=True, command=alias_command("rape"),
          description="回复你要踢出的人或-rape <TelegramID>")
async def rape(context):
    reply = await context.get_reply_message()
    if context.is_group:
        if reply:
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
            if context.sender.last_name is None:
                context_last_name = ''
            else:
                context_last_name = context.sender.last_name
            admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
            if context.sender in admins:
                user = admins[admins.index(context.sender)]
                if not user.participant.admin_rights.ban_users:
                    await context.edit('无封禁用户权限。')
                    return
                try:
                    await context.client.kick_participant(context.chat_id, reply.sender.id)
                except ChatAdminRequiredError:
                    await context.edit('无管理员权限。')
                    return
                except:
                    await context.edit('无法踢出。')
                    return
                await context.client.send_message(
                    context.chat_id,
                    f'[{reply.sender.first_name} {reply_last_name}](tg://user?id={reply.sender.id}) 已被移出群聊',
                    reply_to=reply.id
                )
                try:
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
                        f'[{context.sender.first_name} {context_last_name}](tg://user?id={context.sender.id}) '
                        f'由于乱玩管理员命令 已被禁言60秒',
                        reply_to=reply.id
                    )
                    await context.delete()
                except:
                    pass
        else:
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
            if context.arguments == '':
                return
            else:
                try:
                    userid = int(context.arguments)
                except ValueError:
                    await context.edit('无法识别的账号 id 。')
                    return
                admins = await context.client.get_participants(context.chat, filter=ChannelParticipantsAdmins)
                if context.sender in admins:
                    try:
                        await context.client.kick_participant(context.chat_id, userid)
                        await context.client.send_message(
                            context.chat_id,
                            f'[{userid}](tg://user?id={userid}) 已被移出群聊',
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
                            f'[{context.sender.first_name}{context_last_name}](tg://user?id={context.sender.id}) '
                            f'由于乱玩管理员命令 已被禁言60秒',
                            reply_to=context.id
                        )
                        await context.delete()
                    except:
                        pass
    else:
        pass
