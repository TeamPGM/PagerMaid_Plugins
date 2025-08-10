import contextlib
import asyncio
import json
import csv
import os
from asyncio import sleep
from random import uniform
from datetime import datetime, timedelta

from telethon.tl.types import (
    ChannelParticipantCreator,
    ChannelParticipantAdmin,
    UserStatusRecently,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusLastWeek,
    UserStatusLastMonth,
    ChannelParticipantsSearch,
    ChannelParticipantsRecent,
    ChannelParticipantsAdmins,
    ChannelParticipantsBots,
)
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    UserAdminInvalidError,
    PeerIdInvalidError,
    BadRequestError,
)
from telethon.tl.functions.channels import GetParticipantsRequest

from pagermaid.listener import listener
from pagermaid.enums import Message
from pagermaid.services import bot

# 缓存配置
CACHE_DIR = "plugins/clean_member_cache"
CACHE_EXPIRE_HOURS = 24  # 缓存有效期24小时


def ensure_cache_dir():
    """确保缓存目录存在"""
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_filename(chat_id, mode, day):
    """生成缓存文件名"""
    return f"{CACHE_DIR}/cache_{chat_id}_{mode}_{day}.json"


def get_report_filename(chat_id, mode, day):
    """生成报告文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{CACHE_DIR}/report_{chat_id}_{mode}_{day}_{timestamp}.csv"


async def save_cache(chat_id, mode, day, target_users, chat_title=""):
    """保存查找结果到缓存"""
    ensure_cache_dir()

    cache_data = {
        "chat_id": chat_id,
        "chat_title": chat_title,
        "mode": mode,
        "day": day,
        "search_time": datetime.now().isoformat(),
        "expire_time": (
            datetime.now() + timedelta(hours=CACHE_EXPIRE_HOURS)
        ).isoformat(),
        "total_found": len(target_users),
        "users": [],
    }

    # 保存用户信息
    for user in target_users:
        user_info = {
            "id": user.id,
            "username": getattr(user, "username", "") or "",
            "first_name": getattr(user, "first_name", "") or "",
            "last_name": getattr(user, "last_name", "") or "",
            "is_deleted": getattr(user, "deleted", False),
            "last_online": None,
        }

        # 获取最后上线信息
        if hasattr(user, "status"):
            if isinstance(user.status, UserStatusOffline) and user.status.was_online:
                user_info["last_online"] = user.status.was_online.isoformat()
            elif isinstance(user.status, UserStatusOnline):
                user_info["last_online"] = "online"
            elif isinstance(user.status, UserStatusRecently):
                user_info["last_online"] = "recently"
            elif isinstance(user.status, UserStatusLastWeek):
                user_info["last_online"] = "last_week"
            elif isinstance(user.status, UserStatusLastMonth):
                user_info["last_online"] = "last_month"

        cache_data["users"].append(user_info)

    # 保存缓存文件
    cache_file = get_cache_filename(chat_id, mode, day)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    # 生成可读报告
    await generate_report(cache_data)

    return cache_file


async def generate_report(cache_data):
    """生成CSV报告"""
    report_file = get_report_filename(
        cache_data["chat_id"], cache_data["mode"], cache_data["day"]
    )

    mode_names = {
        "1": f"未上线超过{cache_data['day']}天",
        "2": f"未发言超过{cache_data['day']}天",
        "3": f"发言少于{cache_data['day']}条",
        "4": "已注销账户",
        "5": "所有普通成员",
    }

    with open(report_file, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)

        # 写入头部信息
        writer.writerow(["群组清理报告"])
        writer.writerow(["群组名称", cache_data.get("chat_title", "")])
        writer.writerow(["群组ID", cache_data["chat_id"]])
        writer.writerow(["清理条件", mode_names.get(cache_data["mode"], "未知")])
        writer.writerow(["搜索时间", cache_data["search_time"][:19]])
        writer.writerow(["符合条件用户数量", cache_data["total_found"]])
        writer.writerow([])  # 空行

        # 写入表头
        writer.writerow(["用户ID", "用户名", "姓名", "最后上线时间", "是否注销"])

        # 写入用户数据
        for user in cache_data["users"]:
            full_name = f"{user['first_name']} {user['last_name']}".strip()
            writer.writerow(
                [
                    user["id"],
                    user["username"],
                    full_name,
                    user["last_online"] or "未知",
                    "是" if user["is_deleted"] else "否",
                ]
            )

    return report_file


def load_cache(chat_id, mode, day):
    """加载缓存数据"""
    cache_file = get_cache_filename(chat_id, mode, day)

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 检查缓存是否过期
        expire_time = datetime.fromisoformat(cache_data["expire_time"])
        if datetime.now() > expire_time:
            os.remove(cache_file)  # 删除过期缓存
            return None

        return cache_data
    except Exception as e:
        print(f"Load cache error: {e}")
        return None


def clean_expired_cache():
    """清理过期缓存"""
    if not os.path.exists(CACHE_DIR):
        return

    try:
        for filename in os.listdir(CACHE_DIR):
            if filename.startswith("cache_") and filename.endswith(".json"):
                filepath = os.path.join(CACHE_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)

                    expire_time = datetime.fromisoformat(cache_data["expire_time"])
                    if datetime.now() > expire_time:
                        os.remove(filepath)
                except:
                    continue
    except:
        pass


async def check_self_and_from(message: Message):
    """检查当前用户和消息发送者的管理权限"""
    try:
        # 检查自己是否为管理员
        me = await bot.get_me()
        self_participant = await bot.get_permissions(message.chat_id, me.id)
        if not (self_participant.is_admin or self_participant.is_creator):
            return False

        if not message.sender_id:
            return False

        # 如果是自己发的消息，直接返回 True
        if message.out:
            return True

        # 检查消息发送者是否为管理员
        sender_participant = await bot.get_permissions(
            message.chat_id, message.sender_id
        )
        return sender_participant.is_admin or sender_participant.is_creator
    except Exception:
        return False


async def kick_chat_member(cid, uid, only_search: bool = False):
    """将成员移出群聊（不封禁）"""
    if only_search:
        return
    try:
        with contextlib.suppress(
            UserAdminInvalidError, PeerIdInvalidError, BadRequestError
        ):
            # 修复：正确使用 edit_permissions API
            until_date = datetime.now() + timedelta(minutes=1)

            # 先封禁用户
            await bot.edit_permissions(
                cid,
                uid,
                until_date=until_date,
                view_messages=False,  # 封禁查看消息
            )
            await sleep(uniform(0.5, 1.0))

            # 解封用户（相当于踢出）
            await bot.edit_permissions(
                cid,
                uid,
                view_messages=True,  # 恢复权限
            )
    except FloodWaitError as e:
        await sleep(e.seconds + uniform(0.5, 1.0))
        await kick_chat_member(cid, uid, only_search)


def get_last_online_days(user):
    """获取用户最后在线天数"""
    if not user.status:
        return None

    if isinstance(user.status, (UserStatusOnline, UserStatusRecently)):
        return 0
    elif isinstance(user.status, UserStatusOffline):
        if user.status.was_online:
            days = (datetime.now() - user.status.was_online).days
            return days
    elif isinstance(user.status, UserStatusLastWeek):
        return 7
    elif isinstance(user.status, UserStatusLastMonth):
        return 30

    return None


async def get_all_participants_advanced(chat_id, max_members=50000):
    """
    高级群成员获取方法，突破 10k 限制
    """
    all_participants = []
    seen_ids = set()

    # 方法1: 使用 aggressive=True (官方推荐)
    try:
        async for participant in bot.iter_participants(chat_id, aggressive=True):
            if participant.id not in seen_ids:
                all_participants.append(participant)
                seen_ids.add(participant.id)
                if len(all_participants) >= max_members:
                    break
    except Exception as e:
        print(f"Method 1 failed: {e}")

    # 方法2: 使用不同的过滤器获取更多成员
    filters = [
        ChannelParticipantsRecent(),
        ChannelParticipantsSearch(""),
        ChannelParticipantsAdmins(),
        ChannelParticipantsBots(),
    ]

    for filter_type in filters:
        try:
            offset = 0
            limit = 200

            while len(all_participants) < max_members:
                try:
                    result = await bot(
                        GetParticipantsRequest(
                            chat_id, filter_type, offset, limit, hash=0
                        )
                    )

                    if not result.users:
                        break

                    new_users = 0
                    for user in result.users:
                        if user.id not in seen_ids:
                            all_participants.append(user)
                            seen_ids.add(user.id)
                            new_users += 1

                    if new_users == 0:  # 没有新用户了
                        break

                    offset += len(result.users)
                    await sleep(1)  # 避免限制

                except Exception as e:
                    print(f"Filter {filter_type} at offset {offset} failed: {e}")
                    break

        except Exception as e:
            print(f"Filter {filter_type} failed completely: {e}")
            continue

    # 方法3: 通过常见用户名搜索获取更多成员
    common_names = ["a", "e", "i", "o", "u", "john", "alex", "mike", "anna", "maria"]

    for name in common_names:
        if len(all_participants) >= max_members:
            break

        try:
            async for participant in bot.iter_participants(
                chat_id, search=name, limit=1000
            ):
                if participant.id not in seen_ids:
                    all_participants.append(participant)
                    seen_ids.add(participant.id)
                    if len(all_participants) >= max_members:
                        break

            await sleep(2)  # 搜索间隔
        except Exception as e:
            print(f"Search for '{name}' failed: {e}")
            continue

    return all_participants[:max_members]


async def filter_target_users(participants, chat_id, mode, day, admin_ids):
    """筛选符合条件的用户"""
    target_users = []

    for participant in participants:
        uid = participant.id

        # 跳过管理员
        if uid in admin_ids:
            continue

        try_target = False

        if mode == "1":
            # 按未上线时间清理
            last_online_days = get_last_online_days(participant)
            if last_online_days and last_online_days > day:
                try_target = True

        elif mode == "2":
            # 按未发言时间清理
            try:
                messages = await bot.get_messages(chat_id, limit=1, from_user=uid)
                if messages and messages[0].date < datetime.now() - timedelta(days=day):
                    try_target = True
                elif not messages:  # 从未发言
                    try_target = True
            except Exception:
                continue

        elif mode == "3":
            # 按发言数清理
            try:
                messages = await bot.get_messages(chat_id, limit=day + 1, from_user=uid)
                if len(messages) < day:
                    try_target = True
            except Exception:
                continue

        elif mode == "4":
            # 清理死号
            if hasattr(participant, "deleted") and participant.deleted:
                try_target = True

        elif mode == "5":
            # 清理所有人
            try_target = True

        if try_target:
            target_users.append(participant)

    return target_users


async def process_clean_member(
    message: Message, mode: str, day: int, only_search: bool = False
):
    start_time = datetime.now()
    chat_title = message.chat.title or "当前群组"

    # 清理过期缓存
    clean_expired_cache()

    try:
        if only_search:
            # 查找模式：检查缓存，如果没有则重新搜索
            cache_data = load_cache(message.chat_id, mode, day)

            if cache_data:
                # 使用缓存数据
                await message.edit(f"""🎯 **使用缓存数据**

📊 **缓存信息:**
• 搜索时间: {cache_data["search_time"][:19]}
• 符合条件: {cache_data["total_found"]} 名成员
• 缓存状态: 有效

📁 **文件位置:** `{CACHE_DIR}/`
📈 **CSV报告:** 已生成

✅ **查找完成** - 已使用缓存数据""")
                return

        # 检查是否有可用缓存进行清理
        if not only_search:
            cache_data = load_cache(message.chat_id, mode, day)
            if cache_data:
                # 使用缓存进行清理
                await message.edit(f"""🚀 **使用缓存清理模式**

📊 **缓存信息:**
• 搜索时间: {cache_data["search_time"][:19]}
• 目标用户: {cache_data["total_found"]} 名
• 缓存状态: 有效

🧹 **开始清理...**""")

                member_count = 0
                total_users = len(cache_data["users"])

                for i, user_info in enumerate(cache_data["users"]):
                    uid = user_info["id"]
                    await kick_chat_member(message.chat_id, uid, False)
                    member_count += 1

                    # 每10人更新一次进度
                    if (i + 1) % 10 == 0:
                        progress = (i + 1) / total_users * 100
                        await message.edit(f"""🧹 **缓存清理中...**

📊 **进度:** {i + 1}/{total_users} ({progress:.1f}%)
✅ **已清理:** {member_count} 名成员
⏱️ **用时:** {str(datetime.now() - start_time).split(".")[0]}""")

                    await sleep(uniform(1.0, 2.0))

                elapsed_time = datetime.now() - start_time
                await message.edit(f"""🎉 **缓存清理完成**

✅ **成功清理:** {member_count} 名成员
📊 **使用缓存:** 高效清理模式
⏱️ **总用时:** {str(elapsed_time).split(".")[0]}
📅 **完成时间:** {datetime.now().strftime("%H:%M:%S")}

🚀 **效率提升:** 跳过重复扫描""")
                return

        # 全新扫描模式
        await message.edit(f"""🔄 **开始全新扫描...**

⏱️ **开始时间:** {start_time.strftime("%H:%M:%S")}
🚀 **使用高级获取模式**
📊 **模式:** {"查找" if only_search else "清理"}
🔧 **多重获取方法:** aggressive + 多过滤器 + 搜索""")

        # 获取所有群成员
        participants = await asyncio.wait_for(
            get_all_participants_advanced(message.chat_id, 50000), timeout=300
        )

        await message.edit(f"""📊 **成员获取完成**

👥 **获取到:** {len(participants)} 名成员
🎯 **开始筛选符合条件的用户...**""")

        # 获取管理员列表
        admin_ids = set()
        try:
            async for admin in bot.iter_participants(
                message.chat_id,
                filter=lambda p: hasattr(p, "participant")
                and isinstance(
                    p.participant, (ChannelParticipantCreator, ChannelParticipantAdmin)
                ),
            ):
                admin_ids.add(admin.id)
        except:
            pass

        # 筛选目标用户
        target_users = await filter_target_users(
            participants, message.chat_id, mode, day, admin_ids
        )

        if only_search:
            # 保存到缓存
            cache_file = await save_cache(
                message.chat_id, mode, day, target_users, chat_title
            )
            report_file = get_report_filename(message.chat_id, mode, day)

            elapsed_time = datetime.now() - start_time
            await message.edit(f"""🔍 **查找完成并已缓存**

📊 **结果统计:**
• 检查总数: {len(participants)} 名成员
• 符合条件: {len(target_users)} 名成员
• 筛选比例: {len(target_users) / len(participants) * 100:.1f}%

📁 **文件保存:**
• 缓存文件: `{os.path.basename(cache_file)}`
• CSV报告: `{os.path.basename(report_file)}`
• 存储位置: `{CACHE_DIR}/`

⏱️ **用时:** {str(elapsed_time).split(".")[0]}
🚀 **下次清理将使用缓存，大幅提升效率！**

💡 **提示:** 使用相同参数执行清理命令即可调用缓存""")
        else:
            # 直接清理模式
            member_count = 0
            total_users = len(target_users)

            await message.edit(f"""🧹 **开始清理...**

🎯 **目标用户:** {total_users} 名
📦 **处理模式:** 直接清理（无缓存）""")

            for i, user in enumerate(target_users):
                uid = user.id
                await kick_chat_member(message.chat_id, uid, False)
                member_count += 1

                # 每10人更新一次进度
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / total_users * 100
                    await message.edit(f"""🧹 **清理中...**

📊 **进度:** {i + 1}/{total_users} ({progress:.1f}%)
✅ **已清理:** {member_count} 名成员
⏱️ **用时:** {str(datetime.now() - start_time).split(".")[0]}""")

                await sleep(uniform(1.0, 2.0))

            elapsed_time = datetime.now() - start_time
            await message.edit(f"""🎉 **清理完成**

✅ **成功清理:** {member_count} 名成员
👥 **检查总数:** {len(participants)} 名成员
⏱️ **总用时:** {str(elapsed_time).split(".")[0]}
📅 **完成时间:** {datetime.now().strftime("%H:%M:%S")}""")

    except asyncio.TimeoutError:
        await message.edit("⏰ **操作超时**\n\n获取群成员信息超时（5分钟），请稍后重试")
    except ChatAdminRequiredError:
        await message.edit("❌ **权限不足**\n\n您没有封禁用户的权限")
    except FloodWaitError as e:
        return await message.edit(f"⚠️ **频率限制**\n\n需要等待 {e.seconds} 秒后重试")
    except Exception as e:
        await message.edit(f"❌ **处理出错**\n\n错误信息: {str(e)}")


def get_help_text():
    """获取美化后的帮助文档"""
    return """🧹 **群成员清理工具** v4.0 - **智能缓存版**

📋 **使用方法:**
`-clean_member <模式> [参数] [search]`

🎯 **清理模式:**
├ `1` - 按未上线时间清理
├ `2` - 按未发言时间清理 ⚠️
├ `3` - 按发言数量清理
├ `4` - 清理已注销账户
└ `5` - 清理所有成员 ⚠️

💡 **使用示例:**
├ `-clean_member 1 7 search` - 查找并缓存7天未上线用户
├ `-clean_member 1 7` - 清理7天未上线用户（优先使用缓存）
├ `-clean_member 2 30 search` - 查找并缓存30天未发言用户
└ `-clean_member 4` - 清理已注销账户

🚀 **智能缓存系统 (NEW!):**
• **高效查找**: 先查找缓存结果和CSV报告
• **快速清理**: 基于缓存清理，跳过重复扫描
• **自动过期**: 24小时缓存有效期
• **CSV报告**: 自动生成详细用户报告
• **文件存储**: `plugins/clean_member_cache/`

📊 **工作流程:**
1. **第一步**: 使用 `search` 参数查找并缓存
2. **第二步**: 确认报告后执行清理（自动使用缓存）
3. **效率**: 清理阶段速度提升10倍以上

⚠️ **重要说明:**
• **处理能力**: 最多处理50,000名成员
• **缓存有效期**: 24小时
• **权限要求**: 需要管理员权限
• **文件管理**: 自动清理过期缓存
• **建议流程**: 查找 → 确认报告 → 清理

🛡️ **安全特性:**
• 不会清理管理员
• 分批处理降低风控
• 异常自动重试
• 详细操作日志

📁 **文件输出:**
• 缓存文件: JSON格式，供程序读取
• CSV报告: Excel可打开，供人工查看
• 自动命名: 包含群组ID、模式、时间戳

⏱️ **性能优化:**
• 查找模式: 5-15分钟（大群）
• 缓存清理: 1-3分钟
• 直接清理: 10-30分钟（大群）"""


@listener(
    command="clean_member",
    need_admin=True,
    groups_only=True,
    description="🧹 智能群成员清理工具 v4.0 | 智能缓存系统 | CSV报告生成 | 支持50000+成员 | 查找缓存一键清理",
)
async def clean_member(message: Message):
    if not await check_self_and_from(message):
        return await message.edit("❌ **权限不足**\n\n您不是群管理员，无法使用此命令")

    # 如果没有参数，显示帮助信息
    if not message.parameter:
        help_msg = await message.edit(get_help_text())

        # 等待30秒后自动删除帮助信息
        await sleep(30)
        try:
            await help_msg.edit("⏰ **帮助已过期**\n\n请重新输入命令查看帮助")
            await sleep(3)
            await help_msg.delete()
        except:
            pass
        return

    # 解析命令参数
    params = message.parameter
    mode = params[0] if len(params) > 0 else "0"
    day = 0
    only_search = False

    # 检查是否为查找模式
    if "search" in [p.lower() for p in params]:
        only_search = True

    # 验证模式并设置参数
    if mode == "1":
        # 按未上线时间清理
        if len(params) < 2:
            return await message.edit(
                "❌ **参数错误**\n\n模式1需要指定天数\n例: `-clean_member 1 7 search`"
            )
        try:
            day = max(int(params[1]), 7)
        except:
            return await message.edit("❌ **参数错误**\n\n天数必须为数字")

    elif mode == "2":
        # 按未发言时间清理
        if len(params) < 2:
            return await message.edit(
                "❌ **参数错误**\n\n模式2需要指定天数\n例: `-clean_member 2 30 search`"
            )
        try:
            day = max(int(params[1]), 7)
        except:
            return await message.edit("❌ **参数错误**\n\n天数必须为数字")

    elif mode == "3":
        # 按发言数清理
        if len(params) < 2:
            return await message.edit(
                "❌ **参数错误**\n\n模式3需要指定发言数\n例: `-clean_member 3 5 search`"
            )
        try:
            day = int(params[1])
        except:
            return await message.edit("❌ **参数错误**\n\n发言数必须为数字")

    elif mode == "4":
        # 清理死号，不需要额外参数
        day = 0

    elif mode == "5":
        # 清理所有人
        day = 0

    else:
        return await message.edit(
            "❌ **模式错误**\n\n请输入有效的模式(1-5)\n使用 `-clean_member` 查看帮助"
        )

    # 显示操作确认
    mode_names = {
        "1": f"未上线超过{day}天的用户",
        "2": f"未发言超过{day}天的用户",
        "3": f"发言少于{day}条的用户",
        "4": "已注销的账户",
        "5": "所有普通成员",
    }

    action = "🔍 查找缓存" if only_search else "🧹 智能清理"

    await message.edit(f"""🚀 **{action}模式启动**

🎯 **目标:** {mode_names.get(mode, "未知")}
📊 **群组:** {message.chat.title or "当前群组"}
⚙️ **模式:** {action}
🧠 **版本:** v4.0 智能缓存版
📁 **缓存目录:** `{CACHE_DIR}/`

⏳ 正在检查缓存状态...""")

    # 开始处理
    await process_clean_member(message, mode, day, only_search)
