""" PagerMaid module for channel help. """

import datetime
import json
from asyncio import sleep
from random import uniform
from typing import Any, List, Literal, Optional, Dict
from telethon import Button
import pytz
from telethon.errors.rpcerrorlist import FloodWaitError, UserIsBlockedError, ChatWriteForbiddenError
from telethon.tl.types import Channel, User, Chat, Message as TelethonMessage

from pagermaid.config import Config
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import bot, scheduler, sqlite
from pagermaid.utils import logs

WHITELIST = [-1001441461877]
AVAILABLE_OPTIONS_TYPE = Literal["silent", "text", "all", "photo", "document", "video", "sticker", "animation", "voice", "audio"]
AVAILABLE_OPTIONS = {"silent", "text", "all", "photo", "document", "video", "sticker", "animation", "voice", "audio"}
HELP_TEXT = """📢 智能转发助手使用说明

🔧 基础命令：
- set [源] [目标] [选项...] - 自动转发消息
- del [序号] - 删除转发规则
- backup [源] [目标] [选项...] - 备份历史消息
- list - 显示当前转发规则
- stats - 查看转发统计
- pause [序号] - 暂停转发
- resume [序号] - 恢复转发
- filter [序号] add [关键词] - 添加过滤关键词
- filter [序号] del [关键词] - 删除过滤关键词
- filter [序号] list - 查看过滤列表

🎯 支持的目标类型：
- 频道/群组 - @username 或 -100...ID
- 个人用户 - @username 或 user_id
- 当前对话 - 使用 "me" 或 "here"

📝 消息类型选项：
- silent, text, photo, document, video, sticker, animation, voice, audio, all

💡 示例：
- `shift set @channel1 @channel2 silent photo`
- `shift del 1`
- `shift pause 1,2`
"""

def check_source_available(chat):
    assert isinstance(chat, (Channel, Chat)) and not getattr(chat, 'noforwards', False)

def check_target_available(entity):
    return isinstance(entity, (User, Chat, Channel))

def is_circular_forward(source_id: int, target_id: int) -> (bool, str):
    if source_id == target_id:
        return True, "不能设置自己到自己的转发规则"
    visited = {source_id}
    current_id = target_id
    for _ in range(20):
        if current_id in visited:
            return True, f"检测到间接循环：{current_id}"
        rule_str = sqlite.get(f"shift.{current_id}")
        if not rule_str:
            break
        try:
            next_id = int(json.loads(rule_str).get('target_id', -1))
            if next_id == -1:
                break
            visited.add(current_id)
            current_id = next_id
        except (json.JSONDecodeError, KeyError, ValueError):
            break
    return False, ""

def get_display_name(entity):
    if not entity: return "未知实体"
    if hasattr(entity, 'username') and entity.username:
        return f"@{entity.username}"
    if isinstance(entity, User):
        return entity.first_name or f"ID: {entity.id}"
    if isinstance(entity, (Chat, Channel)):
        return entity.title or f"ID: {entity.id}"
    return f"ID: {entity.id}"

def normalize_chat_id(entity_or_id):
    """统一chat_id格式，确保频道/群组使用负数格式"""
    if hasattr(entity_or_id, 'id'):
        chat_id = entity_or_id.id
        # 如果是频道或超级群组，转换为负数格式
        if isinstance(entity_or_id, Channel):
            return -1000000000000 - chat_id if chat_id > 0 else chat_id
        elif isinstance(entity_or_id, Chat) and chat_id > 0:
            return -chat_id
        return chat_id
    else:
        # 直接传入的ID
        chat_id = int(entity_or_id)
        # 如果是正数且大于某个阈值，可能是频道ID，转换为负数格式
        if chat_id > 1000000000:
            return -1000000000000 - chat_id
        return chat_id

def get_target_type_emoji(entity):
    if not entity: return "❓"
    if isinstance(entity, User):
        return "🤖" if entity.bot else "👤"
    if isinstance(entity, Channel):
        return "📢" if entity.broadcast else "👥"
    if isinstance(entity, Chat):
        return "👥"
    return "❓"

def update_stats(source_id: int, target_id: int, message_type: str):
    today = datetime.datetime.now(pytz.timezone(Config.TIME_ZONE)).strftime("%Y-%m-%d")
    stats_key = f"shift.stats.{source_id}.{today}"
    try:
        stats = json.loads(sqlite.get(stats_key, '{}'))
    except json.JSONDecodeError:
        stats = {}
    stats["total"] = stats.get("total", 0) + 1
    stats[message_type] = stats.get(message_type, 0) + 1
    sqlite[stats_key] = json.dumps(stats)

def is_message_filtered(message: TelethonMessage, source_id: int) -> bool:
    rule_str = sqlite.get(f"shift.{source_id}")
    if not rule_str: return False
    try:
        keywords = json.loads(rule_str).get("filters", [])
        if not keywords or not message.text: return False
        return any(keyword.lower() in message.text.lower() for keyword in keywords)
    except (json.JSONDecodeError, KeyError): return False

async def resolve_target(client, target_input: str, current_chat_id: int):
    if target_input.lower() in ["me", "here"]: 
        return await client.get_entity(current_chat_id)
    try:
        return await client.get_entity(int(target_input))
    except (ValueError, TypeError):
        return await client.get_entity(target_input)

@listener(command="shift", description=HELP_TEXT, parameters="<sub-command> [arguments]")
async def shift_func(message: Message):
    if not message.parameter:
        sub_commands = ["set", "del", "list", "backup", "pause", "resume", "filter", "stats"]
        keyboard = [Button.inline(cmd, data=f"shift {cmd}") for cmd in sub_commands]
        keyboard = [keyboard[i:i+3] for i in range(0, len(keyboard), 3)]
        await message.edit(HELP_TEXT, buttons=keyboard)

@shift_func.sub_command(command="set")
async def shift_func_set(message: Message):
    params = message.parameter[1:]
    if len(params) < 1:
        return await message.edit("参数不足\n\n用法: shift set <目标> [选项...]\n或: shift set <源> <目标> [选项...]")
    
    if len(params) == 1:
        source_input = "here"
        target_input = params[0]
        options = set()
    else:
        source_input = params[0]
        target_input = params[1]
        options = set(params[2:]).intersection(AVAILABLE_OPTIONS)
    
    logs.info(f"[SHIFT] 设置转发规则: source_input={source_input}, target_input={target_input}, options={options}")
    
    try:
        if source_input.lower() in ["here", "me"]:
            source = await message.client.get_entity(message.chat_id)
        else:
            source = await resolve_target(message.client, source_input, message.chat_id)
        check_source_available(source)
        logs.info(f"[SHIFT] 源解析成功: {source.id} ({get_display_name(source)})")
    except Exception as e:
        logs.error(f"[SHIFT] 源对话无效: {e}")
        return await message.edit(f"源对话无效: {e}")
    
    try:
        target = await resolve_target(message.client, target_input, message.chat_id)
        check_target_available(target)
        logs.info(f"[SHIFT] 目标解析成功: {target.id} ({get_display_name(target)})")
    except Exception as e:
        logs.error(f"[SHIFT] 目标对话无效: {e}")
        return await message.edit(f"目标对话无效: {e}")
    
    source_id = normalize_chat_id(source)
    target_id = normalize_chat_id(target)
    is_circular, msg = is_circular_forward(source_id, target_id)
    if is_circular:
        logs.warning(f"[SHIFT] 检测到循环转发: {msg}")
        return await message.edit(f"循环转发: {msg}")
    
    rule = {
        "target_id": target_id,
        "options": list(options),
        "target_type": "user" if isinstance(target, User) else "chat",
        "paused": False,
        "created_at": datetime.datetime.now().isoformat(),
        "filters": []
    }
    sqlite[f"shift.{source_id}"] = json.dumps(rule)
    logs.info(f"[SHIFT] 成功设置转发: {source_id} -> {target_id}")
    await message.edit(f"成功设置转发: {get_display_name(source)} -> {get_display_name(target)}")

@shift_func.sub_command(command="backup")
async def shift_func_backup(message: Message):
    if len(message.parameter) < 3:
        return await message.edit("❌ 参数不足，请提供源和目标。")

    source_input, target_input = message.parameter[1], message.parameter[2]
    options = set(message.parameter[3:]).intersection(AVAILABLE_OPTIONS)

    try:
        source = await resolve_target(message.client, source_input, message.chat_id)
        check_source_available(source)
    except Exception as e:
        return await message.edit(f"❌ 源对话无效: {e}")

    try:
        target = await resolve_target(message.client, target_input, message.chat_id)
        check_target_available(target)
    except Exception as e:
        return await message.edit(f"❌ 目标对话无效: {e}")

    await message.edit(f"🔄 开始备份从 {get_display_name(source)} 到 {get_display_name(target)} 的历史消息...")
    count = 0
    error_count = 0

    async for msg in message.client.iter_messages(source.id):
        await sleep(uniform(0.5, 1.0))
        try:
            await bot.forward_messages(target.id, [msg.id], from_peer=source.id)
            count += 1
            if count % 50 == 0:
                await message.edit(f"🔄 备份进行中... 已处理 {count} 条消息。")
        except Exception as e:
            error_count += 1
            logs.debug(f"备份消息失败: {e}")

    await message.edit(f"✅ 备份完成！共处理 {count} 条消息，失败 {error_count} 条。")

@shift_func.sub_command(command="del")
async def shift_func_del(message: Message):
    if len(message.parameter) < 2: return await message.edit("请提供序号")
    all_shifts = sorted([k for k in sqlite if k.startswith("shift.") and k.count('.') == 1])
    indices, invalid = parse_indices(message.parameter[1], len(all_shifts))
    deleted_count = 0
    for index in sorted(indices, reverse=True):
        key = all_shifts.pop(index)
        del sqlite[key]
        deleted_count += 1
    msg = f"成功删除 {deleted_count} 条规则。"
    if invalid: msg += f" 无效序号: {', '.join(invalid)}"
    await message.edit(msg)

@shift_func.sub_command(command="stats")
async def shift_func_stats(message: Message):
    stats_keys = [k for k in sqlite.keys() if k.startswith("shift.stats.")]
    if not stats_keys:
        return await message.edit("📊 暂无转发统计数据")

    channel_stats = {}
    for key in stats_keys:
        try:
            parts = key.split(".")
            source_id = int(parts[2])
            date = parts[3]
            if source_id not in channel_stats:
                channel_stats[source_id] = {"total": 0, "dates": {}}
            daily_stats = json.loads(sqlite[key])
            daily_total = daily_stats.get("total", 0)
            channel_stats[source_id]["total"] += daily_total
            channel_stats[source_id]["dates"][date] = daily_total
        except (IndexError, ValueError, json.JSONDecodeError):
            continue

    output = "📊 转发统计报告\n\n"
    for source_id, stats in channel_stats.items():
        source_display, _ = await get_chat_display_name_and_info(message.client, source_id)
        output += f"📤 源: {source_display}\n📈 总转发: {stats['total']} 条\n"
        recent_dates = sorted(stats['dates'].keys(), reverse=True)[:7]
        if recent_dates:
            output += "📅 最近7天:\n"
            for date in recent_dates:
                output += f"  - {date}: {stats['dates'][date]} 条\n"
        output += "\n"
    await message.edit(output)

@shift_func.sub_command(command="list")
async def shift_func_list(message: Message):
    all_shifts = sorted([k for k in sqlite if k.startswith("shift.") and k.count('.') == 1])
    if not all_shifts: return await message.edit("🚫 暂无转发规则\n\n💡 使用 `shift set` 命令创建新的转发规则")
    
    active_count = 0
    paused_count = 0
    filter_count = 0
    
    for key in all_shifts:
        try:
            rule = json.loads(sqlite[key])
            if rule.get("paused"):
                paused_count += 1
            else:
                active_count += 1
            if rule.get("filters"):
                filter_count += 1
        except:
            pass
    
    output = f"✨ 智能转发规则管理\n"
    output += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    output += f"📊 统计信息\n"
    output += f"• 总规则数：{len(all_shifts)} 条\n"
    output += f"• 运行中：{active_count} 条 🟢\n"
    output += f"• 已暂停：{paused_count} 条 🟡\n"
    output += f"• 含过滤：{filter_count} 条 🛡️\n\n"
    
    cache = {}
    for i, key in enumerate(all_shifts, 1):
        try:
            rule = json.loads(sqlite[key])
            source_id, target_id = int(key[6:]), int(rule["target_id"])
            source, source_entity = await get_chat_display_name_and_info(message.client, source_id, cache=cache)
            target, target_entity = await get_chat_display_name_and_info(message.client, target_id, rule.get("target_type", "chat"), cache=cache)
            
            status = "⏸️ 已暂停" if rule.get("paused") else "▶️ 运行中"
            
            created_at = rule.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = "未知时间"
            else:
                time_str = "未知时间"
            
            options = rule.get("options", [])
            if not options or "all" in options:
                type_str = "📝 全部消息"
            else:
                type_icons = {
                    "text": "📝 文本", "photo": "🖼️ 图片", "video": "🎥 视频",
                    "document": "📄 文档", "sticker": "🎭 贴纸", "voice": "🎵 语音",
                    "audio": "🎶 音频", "animation": "🎬 动图", "silent": "🔇 静音"
                }
                type_list = [type_icons.get(opt, f"📌 {opt}") for opt in options if opt != "silent"]
                type_str = " + ".join(type_list) if type_list else "📝 文本"
                if "silent" in options:
                    type_str += " (静音)"
            
            filters = rule.get("filters", [])
            filter_str = f"🚫 {len(filters)} 个关键词" if filters else "✅ 无过滤"
            
            output += f"{i}. {status}\n"
            output += f"   📤 源头： {get_target_type_emoji(source_entity)} {source}\n"
            output += f"   📥 目标： {get_target_type_emoji(target_entity)} {target}\n"
            output += f"   🎯 类型： {type_str}\n"
            output += f"   🛡️ 过滤： {filter_str}\n"
            output += f"   🕒 创建： {time_str}\n\n"
            
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logs.warning(f"[SHIFT] 列表中的规则 {key} 已损坏: {e}")
            output += f"{i}. ⚠️ 规则损坏\n   🚨 错误: {key}\n\n"
    
    output += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    output += f"💡 快速操作提示\n"
    output += f"• shift pause [序号] - 暂停规则\n"
    output += f"• shift resume [序号] - 恢复规则\n"
    output += f"• shift del [序号] - 删除规则\n"
    output += f"• shift stats - 查看转发统计"
    
    await message.edit(output)

@shift_func.sub_command(command="pause")
async def shift_func_pause(message: Message): await toggle_pause_resume(message, True)

@shift_func.sub_command(command="resume")
async def shift_func_resume(message: Message): await toggle_pause_resume(message, False)

async def toggle_pause_resume(message: Message, pause: bool):
    if len(message.parameter) < 2: return await message.edit("请提供序号")
    all_shifts = sorted([k for k in sqlite if k.startswith("shift.") and k.count('.') == 1])
    indices, invalid = parse_indices(message.parameter[1], len(all_shifts))
    count = 0
    for index in indices:
        try:
            rule = json.loads(sqlite[all_shifts[index]])
            rule['paused'] = pause
            sqlite[all_shifts[index]] = json.dumps(rule)
            count += 1
        except (IndexError, json.JSONDecodeError): pass
    action = "暂停" if pause else "恢复"
    msg = f"成功{action} {count} 条规则。"
    if invalid: msg += f" 无效序号: {', '.join(invalid)}"
    await message.edit(msg)

@shift_func.sub_command(command="filter")
async def shift_func_filter(message: Message):
    if len(message.parameter) < 4: return await message.edit("参数不足")
    # 修复参数解析顺序：shift filter [序号] [action] [关键词]
    indices_str, action, keywords = message.parameter[1], message.parameter[2], message.parameter[3:]
    all_shifts = sorted([k for k in sqlite if k.startswith("shift.") and k.count('.') == 1])
    indices, _ = parse_indices(indices_str, len(all_shifts))
    
    if not indices:
        return await message.edit(f"无效的序号: {indices_str}")
    
    updated_count = 0
    for index in indices:
        try:
            key = all_shifts[index]
            rule = json.loads(sqlite[key])
            filters = set(rule.get("filters", []))
            
            if action == 'add': 
                filters.update(keywords)
                updated_count += 1
            elif action == 'del': 
                filters.difference_update(keywords)
                updated_count += 1
            elif action == 'list':
                filter_list = list(filters) if filters else ["无过滤词"]
                await message.edit(f"规则 {index + 1} 的过滤词：\n" + "\n".join(f"• {f}" for f in filter_list))
                return
            else:
                await message.edit(f"无效的操作: {action}，支持: add, del, list")
                return
                
            rule['filters'] = list(filters)
            sqlite[key] = json.dumps(rule)
        except (IndexError, json.JSONDecodeError) as e:
            continue
    
    if action in ['add', 'del']:
        await message.edit(f"已为 {updated_count} 条规则更新过滤词。")

async def get_chat_display_name_and_info(client, chat_id: int, chat_type: str = "chat", cache: Optional[Dict[int, Any]] = None):
    if cache is not None and chat_id in cache: entity = cache[chat_id]
    else:
        try: entity = await client.get_entity(chat_id)
        except: entity = None
        if cache is not None: cache[chat_id] = entity
    return get_display_name(entity), entity

def parse_indices(indices_str: str, total: int) -> (List[int], List[str]):
    indices, invalid = [], []
    for i in indices_str.split(','):
        try:
            idx = int(i.strip()) - 1
            if 0 <= idx < total: indices.append(idx)
            else: invalid.append(i)
        except ValueError: invalid.append(i)
    return indices, invalid

def get_media_type(message: TelethonMessage) -> str:
    for media_type in AVAILABLE_OPTIONS: 
        if hasattr(message, media_type) and getattr(message, media_type): return media_type
    return "text"

def get_chat_id_from_message(message: TelethonMessage) -> int:
    """从消息中获取标准化的chat_id"""
    if hasattr(message, 'chat_id'):
        return message.chat_id
    elif hasattr(message, 'peer_id'):
        if hasattr(message.peer_id, 'channel_id'):
            return -1000000000000 - message.peer_id.channel_id
        elif hasattr(message.peer_id, 'chat_id'):
            return -message.peer_id.chat_id
        elif hasattr(message.peer_id, 'user_id'):
            return message.peer_id.user_id
    return None

# 修复后的核心监听器
@listener(is_plugin=True, incoming=True, ignore_edited=True, ignore_forwarded=False, outgoing=True)
async def shift_channel_message(message: TelethonMessage):
    try:
        if not message or not message.chat:
            return
            
        # 获取标准化的source_id
        source_id = get_chat_id_from_message(message)
        if not source_id:
            return
            
        logs.debug(f"[SHIFT] 收到消息: source_id={source_id}, msg_id={message.id}")
        
        # 检查转发规则
        rule_str = sqlite.get(f"shift.{source_id}")
        if not rule_str:
            return
            
        try:
            rule = json.loads(rule_str)
        except json.JSONDecodeError:
            logs.error(f"[SHIFT] 规则解析失败: {rule_str}")
            return
            
        # 检查规则状态
        if rule.get("paused", False):
            return
            
        target_id = rule.get("target_id")
        if not target_id:
            return
            
        # 检查内容保护
        if hasattr(message.chat, 'noforwards') and message.chat.noforwards:
            logs.warning(f"[SHIFT] 源聊天 {source_id} 开启了内容保护，删除转发规则")
            sqlite.pop(f"shift.{source_id}", None)
            return
            
        # 检查消息过滤
        if is_message_filtered(message, source_id):
            logs.debug(f"[SHIFT] 消息被过滤: {source_id}")
            return
            
        # 检查消息类型
        options = rule.get("options", [])
        message_type = get_media_type(message)
        if options and "all" not in options and message_type not in options:
            logs.debug(f"[SHIFT] 消息类型不匹配: {message_type} not in {options}")
            return
            
        # 执行转发
        logs.info(f"[SHIFT] 开始转发: {source_id} -> {target_id}, msg={message.id}")
        await shift_forward_message(source_id, int(target_id), message.id)
        
        # 更新统计
        update_stats(source_id, int(target_id), message_type)
        
    except Exception as e:
        logs.error(f"[SHIFT] 处理消息时出错: {e}")

# 修复后的转发函数
async def shift_forward_message(from_chat_id: int, to_chat_id: int, message_id: int, _depth: int = 0):
    """执行消息转发，支持多级转发"""
    if _depth > 5:
        logs.warning(f"[SHIFT] 转发深度超限: {_depth}")
        return
    
    try:
        # 执行转发
        result = await bot.forward_messages(
            entity=to_chat_id,
            messages=[message_id],
            from_peer=from_chat_id
        )
        
        logs.info(f"[SHIFT] 转发成功: {from_chat_id} -> {to_chat_id}, msg={message_id}, depth={_depth}")
        
        # 检查目标是否有下级转发规则
        next_rule_str = sqlite.get(f"shift.{to_chat_id}")
        if next_rule_str:
            try:
                next_rule = json.loads(next_rule_str)
                if not next_rule.get("paused") and next_rule.get("target_id"):
                    next_target_id = int(next_rule["target_id"])
                    
                    # 短暂延迟，确保消息已送达
                    await sleep(0.2)
                    
                    # 获取刚转发的消息ID
                    try:
                        # 获取目标聊天的最新消息
                        latest_msgs = await bot.get_messages(to_chat_id, limit=1)
                        if latest_msgs and latest_msgs[0]:
                            new_msg_id = latest_msgs[0].id
                            logs.info(f"[SHIFT] 发现下级转发规则: {to_chat_id} -> {next_target_id}, new_msg={new_msg_id}")
                            
                            # 递归转发
                            await shift_forward_message(to_chat_id, next_target_id, new_msg_id, _depth + 1)
                        else:
                            logs.warning(f"[SHIFT] 无法获取新消息，使用原消息ID: {message_id}")
                            await shift_forward_message(to_chat_id, next_target_id, message_id, _depth + 1)
                            
                    except Exception as e:
                        logs.error(f"[SHIFT] 获取新消息失败: {e}")
                        # fallback: 使用原消息ID继续转发
                        await shift_forward_message(to_chat_id, next_target_id, message_id, _depth + 1)
                        
            except Exception as e:
                logs.error(f"[SHIFT] 解析下级规则失败: {e}")
                
    except FloodWaitError as e:
        logs.warning(f"[SHIFT] FloodWait {e.seconds}s, 等待重试")
        await sleep(e.seconds + 1)
        try:
            await bot.forward_messages(to_chat_id, [message_id], from_peer=from_chat_id)
            logs.info(f"[SHIFT] 重试转发成功: {from_chat_id} -> {to_chat_id}")
        except Exception as retry_e:
            logs.error(f"[SHIFT] 重试转发失败: {retry_e}")
            
    except (UserIsBlockedError, ChatWriteForbiddenError) as e:
        logs.warning(f"[SHIFT] 转发失败，权限问题: {e}")
        
    except Exception as e:
        logs.error(f"[SHIFT] 转发失败: {e}")
