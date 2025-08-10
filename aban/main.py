from telethon.tl.functions.channels import EditBannedRequest, GetParticipantRequest
from telethon.tl.types import (
    ChatBannedRights,
    InputPeerUser,
    InputPeerChannel,
)
from datetime import datetime, timedelta

import asyncio
import time

from pagermaid.listener import listener
from pagermaid.utils import logs

# 全局缓存 - 增强版
_CACHE = {
    "groups": {
        "timestamp": 0,
        "data": [],
        "lock": asyncio.Lock(),  # 添加锁防止并发问题
    },
    "permissions": {},  # 缓存每个群组的权限状态
    "entities": {},  # 缓存用户实体
}

# 配置常量
# 将缓存有效期改为永久：使用 None 表示不过期
CACHE_DURATION = None  # None = 永久有效
BATCH_SIZE = 20  # 并发处理的批次大小（提高以加速批量操作）
UPDATE_INTERVAL = 10  # 每处理10个群组更新一次状态

# 加速相关配置
PARALLEL_LIMIT = 8  # 跨群解析/探测的并发度
USE_GET_PARTICIPANT_FIRST = (
    True  # 解析优先策略：优先使用 GetParticipantRequest 精确探测
)
PER_GROUP_SCAN_LIMIT = 2000  # 回退成员遍历时每群的扫描上限


async def smart_edit(message, text, delete_after=14):
    """统一的智能编辑函数"""
    try:
        msg = await message.edit(text)
        if delete_after > 0:
            asyncio.create_task(_auto_delete(msg, delete_after))
        return msg
    except Exception as e:
        logs.error(f"[AdvancedBan] Edit error: {e}")
        return message


async def _auto_delete(message, delay):
    """延迟删除消息"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass


def parse_args(parameter):
    """解析命令参数"""
    if isinstance(parameter, str):
        return parameter.split() if parameter else []
    return parameter if isinstance(parameter, list) else []


async def safe_get_entity(client, target):
    """安全获取用户实体"""
    try:
        target_str = str(target)
        entity = None

        # # 组装缓存键：用户名，ID 直接用字符串
        # cache_key = target_str if target_str.startswith("@") else target_str

        # # 命中实体缓存则直接返回
        # ent_cache = _CACHE.get('entities', {})
        # ent_item = ent_cache.get(cache_key)
        # if ent_item and (CACHE_DURATION is None or (time.time() - ent_item['timestamp'] < CACHE_DURATION)):
        #     return ent_item['data']

        if target_str.startswith("@"):
            entity = await client.get_entity(target)
        elif target_str.lstrip("-").isdigit():
            user_id = int(target)
            entity = await client.get_entity(user_id)
        else:
            raise ValueError("已禁用容易定位错用户的处理用户名（不带@）的逻辑")

        # # 写入缓存
        # try:
        #     ent_cache[cache_key] = {"data": entity, "timestamp": time.time()}
        # except Exception:
        #     pass

        return entity
    except Exception as e:
        logs.error(f"[AdvancedBan] Get entity error for {target}: {e}")
        return None


async def get_target_user(client, message, args):
    """获取目标用户 - 修复版（支持频道马甲身份）
    调整优先级：若命令显式提供了 @username / user_id / 群聊(频道)ID，则优先使用；否则再回退到回复消息。
    """
    # 1) 如果提供了参数，只按参数解析；参数无效则直接返回失败（不回退回复对象）
    try:
        if args:
            raw = str(args[0])

            if raw.startswith("@"):
                entity = await safe_get_entity(client, raw)
                return entity, (entity.id if entity else None)
            elif raw.lstrip("-").isdigit():
                user_id = int(raw)
                entity = await safe_get_entity(client, user_id)
                return entity, user_id
            else:
                # 明确禁止不带@的用户名，保持原有安全策略
                raise ValueError("已禁用容易定位错用户的处理用户名（不带@）的逻辑")
    except Exception as e:
        logs.error(f"[AdvancedBan] Get user from args error: {e}")
        return None, None

    # 2) 未提供参数：仅在“作为回复使用命令”时采用被回复对象
    try:
        if not args and hasattr(message, "reply_to_msg_id") and message.reply_to_msg_id:
            reply_msg = await message.get_reply_message()
            if reply_msg and reply_msg.sender_id:
                target_user = reply_msg.sender
                target_uid = reply_msg.sender_id

                # 检查是否是频道身份发送的消息
                if hasattr(reply_msg, "post") and reply_msg.post:
                    if hasattr(reply_msg, "from_id") and reply_msg.from_id:
                        if hasattr(reply_msg.from_id, "channel_id"):
                            target_uid = reply_msg.from_id.channel_id
                            logs.info(
                                f"[AdvancedBan] Detected channel message, using channel ID: {target_uid}"
                            )

                return target_user, target_uid
    except Exception:
        pass

    # 3) 都无法获取
    return None, None


def format_user(user, user_id):
    """格式化用户显示（支持频道身份）"""
    if user and hasattr(user, "first_name"):
        name = user.first_name or str(user_id)
        if getattr(user, "last_name", None):
            name += f" {user.last_name}"
        if getattr(user, "username", None):
            name += f" (@{user.username})"
        return name
    elif user and hasattr(user, "title"):
        title = user.title
        if getattr(user, "username", None):
            title += f" (@{user.username})"
        return f"频道: {title}"
    elif user and hasattr(user, "broadcast"):
        title = getattr(user, "title", str(user_id))
        if getattr(user, "username", None):
            title += f" (@{user.username})"
        return f"频道: {title}"
    return str(user_id)


async def check_permissions(client, chat_id, action="ban"):
    """检查机器人权限"""
    try:
        # 读取缓存
        perm_cache = _CACHE["permissions"].get(chat_id)
        if perm_cache and (
            CACHE_DURATION is None
            or (time.time() - perm_cache["timestamp"] < CACHE_DURATION)
        ):
            return perm_cache["data"]

        me = await client.get_me()
        part = await client(GetParticipantRequest(chat_id, me.id))
        rights = getattr(part.participant, "admin_rights", None)
        result = bool(rights and rights.ban_users)

        # 写入缓存
        _CACHE["permissions"][chat_id] = {"data": result, "timestamp": time.time()}
        return result
    except Exception:
        return False


async def is_admin(client, chat_id, user_id):
    """检查用户是否为管理员"""
    try:
        part = await client(GetParticipantRequest(chat_id, user_id))
        return getattr(part.participant, "admin_rights", None) is not None
    except Exception:
        return False


async def get_managed_groups(client):
    """获取管理的群组（带缓存）"""
    try:
        # 命中缓存直接返回
        grp_cache = _CACHE["groups"]
        now = time.time()
        if grp_cache["data"] and (
            CACHE_DURATION is None or (now - grp_cache["timestamp"] < CACHE_DURATION)
        ):
            return grp_cache["data"]

        # 缓存过期时，使用锁防止并发重复拉取
        async with grp_cache["lock"]:
            # 进入锁后再次检查是否已有其他协程刷新
            if grp_cache["data"] and (
                CACHE_DURATION is None
                or (time.time() - grp_cache["timestamp"] < CACHE_DURATION)
            ):
                return grp_cache["data"]

            groups = []
            me = await client.get_me()

            # 收集所有对话
            dialogs = []
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    dialogs.append(dialog)

            # 并发检查权限
            async def check_group(dialog):
                try:
                    part = await client(GetParticipantRequest(dialog.id, me.id))
                    rights = getattr(part.participant, "admin_rights", None)
                    if rights and rights.ban_users:
                        return {"id": dialog.id, "title": dialog.title}
                except Exception:
                    pass
                return None

            # 分批并发处理
            for i in range(0, len(dialogs), 10):
                batch = dialogs[i : i + 10]
                results = await asyncio.gather(
                    *[check_group(d) for d in batch], return_exceptions=True
                )
                groups.extend(
                    [r for r in results if r and not isinstance(r, Exception)]
                )

            # 更新缓存
            grp_cache["data"] = groups
            grp_cache["timestamp"] = time.time()
            logs.info(f"[AdvancedBan] Groups refreshed: {len(groups)}")
            return groups
    except Exception as e:
        logs.error(f"[AdvancedBan] Get groups error: {e}")
        return []


def show_help(command):
    """简化的帮助系统"""
    helps = {
        "main": "🛡️ **高级封禁管理插件**\n\n**可用指令：**\n• `kick` - 踢出用户\n• `ban` - 封禁用户\n• `unban` - 解封用户\n• `mute` - 禁言用户\n• `unmute` - 解除禁言\n• `sb` - 批量封禁\n• `unsb` - 批量解封\n• `refresh` - 刷新群组缓存（有效期：永久有效）\n• `preload` - 预加载群组缓存（缓存有效期：永久有效）\n• `cache` - 查看缓存状态（有缓存时显示“⏱️ 永久有效”）\n\n💡 **使用方式：**\n支持：回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名",
        "sb": "🌐 **批量封禁**\n\n**语法：** `sb <用户> [原因]`\n**示例：** `sb @user 垃圾广告`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n在你管理的所有群组中封禁指定用户",
        "unsb": "🌐 **批量解封**\n\n**语法：** `unsb <用户>`\n**示例：** `unsb @user`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n在你管理的所有群组中解封指定用户",
        "kick": "🚪 **踢出用户**\n\n**语法：** `kick <用户> [原因]`\n**示例：** `kick @user 刷屏`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n用户可以重新加入群组",
        "ban": "🚫 **封禁用户**\n\n**语法：** `ban <用户> [原因]`\n**示例：** `ban @user 广告`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n永久封禁，需要管理员解封",
        "unban": "🔓 **解除封禁**\n\n**语法：** `unban <用户>`\n**示例：** `unban @user`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n解除用户封禁状态",
        "mute": "🤐 **禁言用户**\n\n**语法：** `mute <用户> [分钟] [原因]`\n**示例：** `mute @user 60 刷屏`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n默认60分钟，最长24小时",
        "unmute": "🔊 **解除禁言**\n\n**语法：** `unmute <用户>`\n**示例：** `unmute @user`\n**支持：** 回复消息、@用户名、用户ID、群/频道ID（负数）\n不支持：不带 @ 的用户名\n\n立即解除禁言",
        "refresh": "🔄 **刷新群组缓存**\n\n重建管理群组缓存。\n显示：`有效期：永久有效`",
        "preload": "⚡ **预加载群组缓存**\n\n预先建立管理群组缓存以加速后续操作。\n显示：`缓存有效期：永久有效`",
        "cache": "🗃️ **查看缓存状态**\n\n显示当前缓存信息。\n当有缓存时显示：`⏱️ 永久有效`；否则显示：`尚未建立缓存`",
    }
    return helps.get(command, helps["main"])


async def handle_user_action(client, message, command):
    """统一的用户操作处理"""
    if not (getattr(message, "out", True) or getattr(message, "outgoing", True)):
        return None

    args = parse_args(getattr(message, "parameter", "") or "")

    # 检查是否需要显示帮助
    has_reply = hasattr(message, "reply_to_msg_id") and message.reply_to_msg_id
    if not args and not has_reply:
        await smart_edit(message, show_help(command), 30)
        return None

    if not hasattr(message, "chat_id"):
        await smart_edit(message, "❌ 此命令只能在群组中使用")
        return None

    user, uid = await get_target_user(client, message, args)
    if not uid:
        await smart_edit(message, "❌ 无法获取用户信息")
        return None

    return user, uid, args


async def safe_ban_action(client, chat_id, user_id, rights):
    """安全的封禁操作函数（支持频道马甲身份并删除消息）"""
    try:
        ban_success = False

        try:
            await client(EditBannedRequest(chat_id, user_id, rights))
            ban_success = True
        except Exception as e1:
            logs.error(f"[AdvancedBan] Method 1 (direct ID) failed: {e1}")

            try:
                user_entity = await safe_get_entity(client, user_id)
                if user_entity:
                    await client(EditBannedRequest(chat_id, user_entity, rights))
                    ban_success = True
            except Exception as e2:
                logs.error(f"[AdvancedBan] Method 2 (entity) failed: {e2}")

                try:
                    from telethon.tl.functions.channels import GetParticipantRequest

                    participant = await client(GetParticipantRequest(chat_id, user_id))
                    if hasattr(participant.participant, "peer") and hasattr(
                        participant.participant.peer, "channel_id"
                    ):
                        channel_id = participant.participant.peer.channel_id
                        await client(EditBannedRequest(chat_id, channel_id, rights))
                        logs.info(
                            f"[AdvancedBan] Banned channel identity: {channel_id}"
                        )
                        ban_success = True
                except Exception as e3:
                    logs.error(
                        f"[AdvancedBan] Method 3 (channel identity) failed: {e3}"
                    )

                if not ban_success:
                    try:
                        user_entity = await safe_get_entity(client, user_id)
                        if (
                            user_entity
                            and hasattr(user_entity, "access_hash")
                            and user_entity.access_hash
                        ):
                            if (
                                hasattr(user_entity, "broadcast")
                                and user_entity.broadcast
                            ):
                                input_peer = InputPeerChannel(
                                    user_id, user_entity.access_hash
                                )
                            else:
                                input_peer = InputPeerUser(
                                    user_id, user_entity.access_hash
                                )

                            await client(EditBannedRequest(chat_id, input_peer, rights))
                            ban_success = True
                    except Exception as e4:
                        logs.error(f"[AdvancedBan] Method 4 (InputPeer) failed: {e4}")

        # 如果是永久封禁（view_messages=True），尝试删除该用户的消息
        if getattr(rights, "view_messages", False):
            try:
                from telethon.tl.functions.channels import (
                    DeleteParticipantHistoryRequest,
                )

                try:
                    await client(
                        DeleteParticipantHistoryRequest(
                            channel=chat_id, participant=user_id
                        )
                    )
                    logs.info(
                        f"[AdvancedBan] Deleted all messages from user {user_id} in chat {chat_id}"
                    )
                except Exception as e1:
                    logs.error(f"[AdvancedBan] Method 1 delete failed: {e1}")
                    try:
                        user_entity = await safe_get_entity(client, user_id)
                        if user_entity:
                            await client(
                                DeleteParticipantHistoryRequest(
                                    channel=chat_id, participant=user_entity
                                )
                            )
                            logs.info(
                                f"[AdvancedBan] Deleted all messages from user {user_id} in chat {chat_id} (method 2)"
                            )
                    except Exception as e2:
                        logs.error(f"[AdvancedBan] Method 2 delete failed: {e2}")
                        logs.warning(
                            f"[AdvancedBan] Could not delete messages for user {user_id}, but ban was successful"
                        )

            except Exception as e:
                logs.error(f"[AdvancedBan] Failed to delete user messages: {e}")

        return ban_success

    except Exception as e:
        logs.error(f"[AdvancedBan] Safe ban action error: {e}")
        return False


# 批量操作的异步处理函数
async def batch_ban_operation(client, groups, user_id, rights, operation_name="封禁"):
    """批量执行封禁/解封操作（并发优化）"""
    success = 0
    failed = 0
    failed_groups = []

    async def process_group(group):
        try:
            if await safe_ban_action(client, group["id"], user_id, rights):
                return True, None
            else:
                return False, group["title"]
        except Exception as e:
            logs.error(f"[AdvancedBan] {operation_name} error in {group['title']}: {e}")
            return False, f"{group['title']} (异常)"

    # 分批并发处理
    for i in range(0, len(groups), BATCH_SIZE):
        batch = groups[i : i + BATCH_SIZE]
        results = await asyncio.gather(
            *[process_group(g) for g in batch], return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                failed += 1
                failed_groups.append("未知群组 (异常)")
            elif result[0]:
                success += 1
            else:
                failed += 1
                if result[1]:
                    failed_groups.append(result[1])

    return success, failed, failed_groups


# 主要命令实现
@listener(
    is_plugin=True, outgoing=True, command="aban", description="高级封禁管理插件帮助"
)
async def show_main_help(client, message):
    if not (getattr(message, "out", True) or getattr(message, "outgoing", True)):
        return
    await smart_edit(message, show_help("main"), 30)


@listener(is_plugin=True, outgoing=True, command="refresh", description="刷新群组缓存")
async def refresh_cache(client, message):
    """手动刷新群组缓存"""
    if not (getattr(message, "out", True) or getattr(message, "outgoing", True)):
        return

    status = await smart_edit(message, "🔄 正在刷新群组缓存...", 0)

    try:
        # 主动清空并重建群组缓存
        _CACHE["groups"]["data"] = []
        _CACHE["groups"]["timestamp"] = 0
        groups = await get_managed_groups(client)

        # 清理权限和实体缓存（延后按需再生成）
        _CACHE["permissions"].clear()
        _CACHE["entities"].clear()

        # 刷新成功提示
        await status.edit(f"✅ 刷新完成，管理群组数：{len(groups)}")
        return
    except Exception as e:
        try:
            logs.error(f"[AdvancedBan] Refresh cache error: {e}")
        except Exception:
            pass
        await smart_edit(status, f"❌ 刷新失败：{e}")
        return


async def _resolve_user_across_groups_by_id(
    client, groups, uid: int, per_group_limit: int = None
):
    """在已管理的群组中按 user_id 并发尝试解析用户实体。
    策略：
      1) 优先使用 GetParticipantRequest(chat, uid) 精确探测；
      2) 失败时才回退到遍历成员（限量 per_group_limit）。
      3) 命中任意一群即返回该 User 实体，并取消其他探测。
    参数 per_group_limit 为空时，使用全局 PER_GROUP_SCAN_LIMIT。
    返回 Telethon User 实体或 None。
    """
    try:
        # 如果实体缓存已有，直接返回（命中即不再请求网络）
        ent_cache = _CACHE.get("entities", {})
        cache_key = str(uid)
        ent_item = ent_cache.get(cache_key)
        if ent_item and (
            CACHE_DURATION is None
            or (time.time() - ent_item.get("timestamp", 0) < CACHE_DURATION)
        ):
            return ent_item.get("data")
    except Exception:
        pass

    per_limit = per_group_limit or PER_GROUP_SCAN_LIMIT
    semaphore = asyncio.Semaphore(PARALLEL_LIMIT)
    found_user = {"val": None}
    done_event = asyncio.Event()

    async def probe_group(g):
        # g 可能是 dict({'id','title'}) 或 Telethon 实体，统一取 id 与 title
        group_id = None
        group_title = None
        try:
            if isinstance(g, dict):
                group_id = g.get("id")
                group_title = g.get("title")
            else:
                group_id = getattr(g, "id", g)
                group_title = getattr(g, "title", str(group_id))
        except Exception:
            group_id = g
            group_title = str(g)

        if group_id is None:
            return

        async with semaphore:
            if done_event.is_set():
                return
            # 1) 优先用 GetParticipantRequest 探测
            if USE_GET_PARTICIPANT_FIRST:
                try:
                    res = await client(GetParticipantRequest(group_id, uid))
                    # Telethon 返回对象通常包含 users 列表，尝试取匹配的用户
                    users_list = getattr(res, "users", None)
                    if users_list:
                        for u in users_list:
                            if getattr(u, "id", None) == uid:
                                found_user["val"] = u
                                done_event.set()
                                return
                except Exception:
                    # 未命中或无权限等，进入成员遍历回退
                    pass

            if done_event.is_set():
                return

            # 2) 回退遍历成员（限量）
            try:
                async for p in client.iter_participants(group_id, limit=per_limit):
                    if getattr(p, "id", None) == uid:
                        found_user["val"] = p
                        done_event.set()
                        return
            except Exception as e:
                try:
                    logs.error(
                        f"[AdvancedBan] Scan group {group_title} for uid {uid} error: {e}"
                    )
                except Exception:
                    pass

    # 并发发起探测
    tasks = [asyncio.create_task(probe_group(g)) for g in groups]
    try:
        # 等待首个命中或所有任务结束
        while not done_event.is_set() and any(not t.done() for t in tasks):
            await asyncio.sleep(0.05)
    finally:
        if done_event.is_set():
            # 取消仍在运行的任务
            for t in tasks:
                if not t.done():
                    t.cancel()
        # 收尾等待但忽略异常
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass

    user = found_user["val"]
    # 写入实体缓存（遵循全局 CACHE_DURATION 策略）
    if user is not None:
        try:
            ent_cache = _CACHE.get("entities", {})
            ent_cache[str(uid)] = {"data": user, "timestamp": time.time()}
        except Exception:
            pass
    return user


@listener(
    is_plugin=True,
    outgoing=True,
    command="sb",
    description="批量封禁用户",
    parameters="<用户> [原因]",
)
async def super_ban(client, message):
    result = await handle_user_action(client, message, "sb")
    if not result:
        return
    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试在“已管理群组”中进行限量扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            # 解析成功，继续后续批量封禁流程
            user = found
            uid = getattr(found, "id", uid)
            message = status  # 复用状态消息，后续会继续编辑
    except Exception:
        pass

    reason = " ".join(args[1:]) if len(args) > 1 else "跨群违规"
    display = format_user(user, uid)
    status = await smart_edit(message, "🌐 正在查找与目标用户的共同群组...", 0)
    try:
        # 使用缓存的“管理的群组”，避免逐群扫描共同群组
        groups = await get_managed_groups(client)

        if not groups:
            await smart_edit(
                status, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
            )
            return

        await status.edit(
            f"🌐 正在批量封禁 {display}...\n📊 目标群组：{len(groups)} 个"
        )

        rights = ChatBannedRights(
            until_date=None,
            view_messages=True,
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
        )

        success, failed, failed_groups = await batch_ban_operation(
            client, groups, uid, rights, operation_name="封禁"
        )

        result_text = (
            f"✅ **批量封禁完成**\n\n"
            f"👤 用户：{display}\n"
            f"🆔 ID：`{uid}`\n"
            f"📝 原因：{reason}\n"
            f"🌐 成功：{success} 群组\n"
            f"❌ 失败：{failed} 群组\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        if failed_groups and len(failed_groups) <= 3:
            result_text += "\n\n失败群组：\n" + "\n".join(
                f"• {g}" for g in failed_groups[:3]
            )
        await smart_edit(status, result_text, 60)
    except Exception as e:
        await smart_edit(status, f"❌ sb执行异常：{e}")


@listener(
    is_plugin=True,
    outgoing=True,
    command="unsb",
    description="批量解封用户",
    parameters="<用户>",
)
async def super_unban(client, message):
    result = await handle_user_action(client, message, "unsb")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试在“已管理群组”中进行限量扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass

    display = format_user(user, uid)

    status = await smart_edit(message, "🌐 正在获取管理群组...", 0)

    # 预加载缓存（如果需要）
    groups = await get_managed_groups(client)

    if not groups:
        return await smart_edit(
            status, "❌ 未找到管理的群组\n\n💡 提示：使用 `refresh` 命令刷新缓存"
        )

    await status.edit(f"🌐 正在批量解封 {display}...\n📊 目标群组：{len(groups)} 个")

    # 设置解封权限
    rights = ChatBannedRights(until_date=0)

    # 记录开始时间
    start_time = time.time()

    # 执行批量解封
    success, failed, failed_groups = await batch_ban_operation(
        client, groups, uid, rights, "解封"
    )

    # 计算耗时
    elapsed = time.time() - start_time

    result_text = f"✅ **批量解封完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n🌐 成功：{success} 群组\n❌ 失败：{failed} 群组\n⏱️ 耗时：{elapsed:.1f} 秒\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

    if failed_groups and len(failed_groups) <= 3:
        result_text += f"\n\n失败群组：\n" + "\n".join(
            f"• {g}" for g in failed_groups[:3]
        )

    await smart_edit(status, result_text, 60)


@listener(
    is_plugin=True,
    outgoing=True,
    command="kick",
    description="踢出用户",
    parameters="<用户> [原因]",
)
async def kick_user(client, message):
    result = await handle_user_action(client, message, "kick")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试跨群扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass
    reason = " ".join(args[1:]) if len(args) > 1 else "广告"
    display = format_user(user, uid)

    status = await smart_edit(message, f"🚪 正在踢出 {display}...", 0)

    if await is_admin(client, message.chat_id, uid):
        return await smart_edit(status, "❌ 不能踢出管理员")

    if not await check_permissions(client, message.chat_id):
        return await smart_edit(status, "❌ 权限不足")

    try:
        # 先封禁再解封实现踢出
        ban_rights = ChatBannedRights(until_date=0, view_messages=True)
        await safe_ban_action(client, message.chat_id, uid, ban_rights)

        unban_rights = ChatBannedRights(until_date=0)
        await safe_ban_action(client, message.chat_id, uid, unban_rights)

        result_text = f"✅ **踢出完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n📝 原因：{reason}\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        await smart_edit(status, result_text)
    except Exception as e:
        await smart_edit(status, f"❌ 踢出失败：{str(e)}")


@listener(
    is_plugin=True,
    outgoing=True,
    command="ban",
    description="封禁用户",
    parameters="<用户> [原因]",
)
async def ban_user(client, message):
    result = await handle_user_action(client, message, "ban")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试跨群扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass
    reason = " ".join(args[1:]) if len(args) > 1 else "广告"
    display = format_user(user, uid)

    status = await smart_edit(message, f"🚫 正在封禁 {display}...", 0)

    if await is_admin(client, message.chat_id, uid):
        return await smart_edit(status, "❌ 不能封禁管理员")

    if not await check_permissions(client, message.chat_id):
        return await smart_edit(status, "❌ 权限不足")

    rights = ChatBannedRights(until_date=None, view_messages=True, send_messages=True)
    success = await safe_ban_action(client, message.chat_id, uid, rights)

    if success:
        result_text = f"✅ **封禁完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n📝 原因：{reason}\n🗑️ 已删除该用户的所有消息\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        await smart_edit(status, result_text)
    else:
        await smart_edit(status, "❌ 封禁失败，请检查权限或用户是否存在")


@listener(
    is_plugin=True,
    outgoing=True,
    command="unban",
    description="解封用户",
    parameters="<用户>",
)
async def unban_user(client, message):
    result = await handle_user_action(client, message, "unban")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试跨群扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass
    display = format_user(user, uid)

    status = await smart_edit(message, f"🔓 正在解封 {display}...", 0)

    if not await check_permissions(client, message.chat_id):
        return await smart_edit(status, "❌ 权限不足")

    rights = ChatBannedRights(until_date=0)
    success = await safe_ban_action(client, message.chat_id, uid, rights)

    if success:
        result_text = f"✅ **解封完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        await smart_edit(status, result_text)
    else:
        await smart_edit(status, "❌ 解封失败，用户可能不在群组或无权限")


@listener(
    is_plugin=True,
    outgoing=True,
    command="mute",
    description="禁言用户",
    parameters="<用户> [分钟] [原因]",
)
async def mute_user(client, message):
    result = await handle_user_action(client, message, "mute")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试跨群扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass
    minutes = 60
    reason = "违规发言"

    # 解析参数
    if len(args) > 1:
        if args[1].isdigit():
            minutes = max(1, min(int(args[1]), 1440))  # 最长24小时
            if len(args) > 2:
                reason = " ".join(args[2:])
        else:
            reason = " ".join(args[1:])

    display = format_user(user, uid)
    status = await smart_edit(message, f"🤐 正在禁言 {display}...", 0)

    if await is_admin(client, message.chat_id, uid):
        return await smart_edit(status, "❌ 不能禁言管理员")

    if not await check_permissions(client, message.chat_id):
        return await smart_edit(status, "❌ 权限不足")

    try:
        until_date = int(datetime.utcnow().timestamp()) + (minutes * 60)
        rights = ChatBannedRights(until_date=until_date, send_messages=True)
        success = await safe_ban_action(client, message.chat_id, uid, rights)

        if success:
            end_time = (datetime.utcnow() + timedelta(minutes=minutes)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            result_text = f"✅ **禁言完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n📝 原因：{reason}\n⏱️ 时长：{minutes} 分钟\n🔓 解除：{end_time} UTC"
            await smart_edit(status, result_text)
        else:
            await smart_edit(status, "❌ 禁言失败，请检查权限")
    except Exception as e:
        await smart_edit(status, f"❌ 禁言失败：{str(e)}")


@listener(
    is_plugin=True,
    outgoing=True,
    command="unmute",
    description="解除禁言",
    parameters="<用户>",
)
async def unmute_user(client, message):
    result = await handle_user_action(client, message, "unmute")
    if not result:
        return

    user, uid, args = result
    # 若为纯数字ID且未直接解析到实体，则尝试跨群扫描解析
    try:
        raw = str(args[0]) if args else ""
        if (
            raw
            and raw.lstrip("-").isdigit()
            and (user is None)
            and isinstance(uid, int)
            and uid > 0
        ):
            status_scan = await smart_edit(
                message, "🔎 未能直接解析该 ID，正在跨群扫描尝试定位实体...", 0
            )
            groups = await get_managed_groups(client)
            if not groups:
                await smart_edit(
                    status_scan, "❌ 未找到可管理的群组（请确认已建立缓存或有管理权限）"
                )
                return
            found = await _resolve_user_across_groups_by_id(
                client, groups, uid, per_group_limit=2000
            )
            if not found:
                return await smart_edit(
                    status_scan,
                    "❌ 无法通过纯数字ID跨群定位该用户\n\n"
                    "请改用：\n"
                    "• @用户名（推荐），或\n"
                    "• 在任一聊天回复该用户后再使用命令，或\n"
                    "• 确保你与该用户有共同群/私聊以便解析实体",
                    30,
                )
            user = found
            uid = getattr(found, "id", uid)
            message = status_scan
    except Exception:
        pass
    display = format_user(user, uid)

    status = await smart_edit(message, f"🔊 正在解除禁言 {display}...", 0)

    if not await check_permissions(client, message.chat_id):
        return await smart_edit(status, "❌ 权限不足")

    rights = ChatBannedRights(until_date=0, send_messages=False)
    success = await safe_ban_action(client, message.chat_id, uid, rights)

    if success:
        result_text = f"✅ **解除禁言完成**\n\n👤 用户：{display}\n🆔 ID：`{uid}`\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        await smart_edit(status, result_text)
    else:
        await smart_edit(status, "❌ 解除禁言失败，请检查权限")


# 添加预加载命令（可选）
@listener(
    is_plugin=True, outgoing=True, command="preload", description="预加载群组缓存"
)
async def preload_cache(client, message):
    """预加载群组缓存，提高后续操作速度"""
    if not (getattr(message, "out", True) or getattr(message, "outgoing", True)):
        return

    status = await smart_edit(message, "🔄 正在预加载缓存...", 0)

    try:
        # 预加载群组
        groups = await get_managed_groups(client)

        # 预加载当前用户信息
        me = await client.get_me()

        info_text = f"✅ **预加载完成**\n\n"
        info_text += f"👤 当前用户：{me.first_name or 'Unknown'}\n"
        info_text += f"📊 管理群组：{len(groups)} 个\n"
        info_text += (
            f"⏰ 缓存有效期：永久有效\n\n"
            if CACHE_DURATION is None
            else f"⏰ 缓存有效期：{CACHE_DURATION} 秒\n\n"
        )
        info_text += f"💡 提示：后续同类操作将更快，如需强制刷新可用 `refresh`"

        await smart_edit(status, info_text, 30)
    except Exception as e:
        await smart_edit(status, f"❌ 预加载失败：{str(e)}")


# 添加缓存状态查看命令（可选）
@listener(is_plugin=True, outgoing=True, command="cache", description="查看缓存状态")
async def cache_status(client, message):
    """查看当前缓存状态"""
    if not (getattr(message, "out", True) or getattr(message, "outgoing", True)):
        return

    try:
        now = time.time()
        grp = _CACHE["groups"]
        age = int(now - grp["timestamp"]) if grp["timestamp"] else None
        if grp["data"]:
            if CACHE_DURATION is None:
                ttl_info = "⏱️ 永久有效"
            else:
                ttl_left = max(0, CACHE_DURATION - age) if age is not None else 0
                ttl_info = f"⏱️ 剩余有效期：{ttl_left} 秒"
        else:
            ttl_info = "⏱️ 尚未建立缓存"
        info = [
            "🗃️ 缓存状态",
            f"📊 群组数：{len(grp['data'])}",
            ttl_info,
            f"🔐 权限缓存项：{len(_CACHE['permissions'])}",
            f"🧩 实体缓存项：{len(_CACHE['entities'])}",
        ]
        await smart_edit(message, "\n".join(info), 30)
    except Exception as e:
        await smart_edit(message, f"❌ 读取缓存状态失败：{e}")


# 清理缓存的辅助函数（定期清理过期缓存）
async def cleanup_cache():
    """清理过期的缓存项"""
    try:
        # 永久缓存时无需清理
        if CACHE_DURATION is None:
            return
        now = time.time()
        # 清理实体缓存
        ent_cache = _CACHE.get("entities", {})
        to_del = [
            k
            for k, v in ent_cache.items()
            if (now - v.get("timestamp", 0)) >= CACHE_DURATION
        ]
        for k in to_del:
            ent_cache.pop(k, None)

        # 清理权限缓存
        perm_cache = _CACHE.get("permissions", {})
        to_del_p = [
            k
            for k, v in perm_cache.items()
            if (now - v.get("timestamp", 0)) >= CACHE_DURATION
        ]
        for k in to_del_p:
            perm_cache.pop(k, None)
    except Exception:
        pass
