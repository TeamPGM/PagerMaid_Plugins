"""PMCaptcha v2 - An plugin a day keeps the ads away
v1 by xtaodata and cloudreflection
v2 by Sam
"""

import asyncio
import gc
import html
import inspect
import json
import re
import time
import traceback
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from io import BytesIO
from random import randint
from typing import Optional, Callable, Union, List, Any, Dict, Coroutine

# Pyrogram imports replaced with Telethon equivalents
from telethon.errors import FloodWaitError
from telethon.errors import RPCError
from telethon.errors.rpcerrorlist import PeerIdInvalidError
from telethon.tl.functions import messages, users
from telethon.tl.functions.account import (
    SetGlobalPrivacySettingsRequest,
    GetGlobalPrivacySettingsRequest,
    UpdateNotifySettingsRequest,
)
from telethon.tl.functions.channels import UpdateUsernameRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.folders import EditPeerFoldersRequest
from telethon.tl.types import (
    GlobalPrivacySettings,
    InputFolderPeer,
    InputNotifyPeer,
    InputPeerNotifySettings,
)
from telethon.tl.types import User, Document

from pagermaid.config import Config
from pagermaid.dependence import sqlite
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import bot
from pagermaid.utils import alias_command, Sub, logs

cmd_name = "pmcaptcha"

lang_version = "2.25"

log_collect_bot = img_captcha_bot = "PagerMaid_Sam_Bot"

# Get alias for user command
user_cmd_name = alias_command(cmd_name)


def _sort_line_number(m):
    try:
        func = getattr(m[1], "__func__", m[1])
        return func.__code__.co_firstlineno
    except AttributeError:
        return -1


async def log(message: str, remove_prefix: bool = False):
    console.info(message.replace("`", '"'))
    Config.LOG and logging.send_log(message, remove_prefix)


def get_version():
    from pagermaid.static import working_dir
    from os import sep
    from json import load

    with open(
        f"{working_dir}{sep}plugins{sep}version.json", "r", encoding="utf-8"
    ) as f:
        version_json = load(f)
    return version_json.get(cmd_name, "unknown")


# region Text Formatting


def code(text: str) -> str:
    return f"<code>{text}</code>"


def italic(text: str) -> str:
    return f"<i>{text}</i>"


def bold(text: str) -> str:
    return f"<b>{text}</b>"


def gen_link(text: str, url: str) -> str:
    return f'<a href="{url}">{text}</a>'


def str_timestamp(unix_ts: int) -> str:
    import datetime

    date_time = datetime.datetime.fromtimestamp(
        unix_ts, datetime.timezone(datetime.timedelta(hours=8))
    )
    return date_time.strftime("%Y-%m-%dT%XZ%z")


# endregion


def get_lang_list():  # Yes, blocking
    from httpx import Client

    endpoint = f"https://raw.githubusercontent.com/TeamPGM/PMCaptcha-i18n/main/v{lang_version}.py"
    for _ in range(3):
        try:
            with Client() as client:
                response = client.get(endpoint)
                if response.status_code == 200:
                    return eval(f"lambda: {response.text}")()
        except Exception as e:
            console.error(f"Failed to get language file: {e}\n{traceback.format_exc()}")
    exit(1)


# Language file
lang_dict = get_lang_list()


def lang(lang_id: str, lang_code: str = Config.LANGUAGE or "en") -> str:
    lang_code = lang_code or "en"
    return lang_dict.get(
        lang_id, [f"Get lang failed[{code(lang_id)}]", f"获取语言失败[{code(lang_id)}]"]
    )[1 if lang_code.startswith("zh") else 0]


def lang_full(lang_id: str, *format_args):
    return "\n".join(
        lang_str % format_args
        for lang_str in lang_dict.get(
            lang_id, [f"Get lang failed[{code(lang_id)}]", f"获取语言失败[{code(lang_id)}]"]
        )
    )


async def exec_api(coro_func: Coroutine):
    for _ in range(3):
        try:
            return await coro_func
        except FloodWaitError as e:
            console.debug(f"API Flood triggered, waiting for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            console.error(f"Function Call Failed: {e}\n{traceback.format_exc()}")
            return None


@dataclass
class Log:
    task: Optional[asyncio.Task] = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    last_send_time: int = 0

    async def worker(self):
        while True:
            text = None
            try:
                if int(time.time()) - self.last_send_time < 5:
                    await asyncio.sleep(5 - (int(time.time()) - self.last_send_time))
                    continue
                (text,) = await self.queue.get()
                await bot.send_message(Config.LOG_ID, text, parse_mode='html')
                self.last_send_time = int(time.time())
            except asyncio.CancelledError:
                break
            except FloodWaitError as e:
                console.debug(f"Flood triggered when sending log, wait for {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                console.error(f"Error when sending log: {e}\n{traceback.format_exc()}")
            finally:
                text and self.queue.task_done()

    def send_log(self, message: str, remove_prefix: bool):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.worker())
        message = message if remove_prefix else " ".join(("[PMCaptcha]", message))
        self.queue.put_nowait((message,))


@dataclass
class Setting:
    key_name: str
    whitelist: Sub = field(init=False)
    pending_ban_list: Sub = field(init=False)
    pending_challenge_list: Sub = field(init=False)

    def __post_init__(self):
        self.whitelist = Sub("pmcaptcha.success")
        self.pending_ban_list = Sub("pmcaptcha.pending_ban")
        self.pending_challenge_list = Sub("pmcaptcha.pending_challenge")

    def get(self, key: str, default=None):
        if sqlite.get(self.key_name) is None:
            return default
        return sqlite[self.key_name].get(key, default)

    def set(self, key: str, value: Any):
        """Set the value of a key in the database, return value"""
        if (data := sqlite.get(self.key_name)) is None:
            sqlite[self.key_name] = data = {}
        data.update({key: value})
        sqlite[self.key_name] = data
        return value

    def delete(self, key: str):
        """Delete a key in the database, if key exists"""
        if self.get(key) is not None:
            data = sqlite[self.key_name]
            del data[key]
            sqlite[self.key_name] = data
        return self

    def is_verified(self, user_id: int) -> bool:
        return self.whitelist.check_id(user_id) or user_id == bot.me.id

    # region Captcha Challenge

    def get_challenge_state(self, user_id: int) -> dict:
        return sqlite.get(f"{self.key_name}.challenge.{user_id}", {})

    def set_challenge_state(self, user_id: int, state: dict):
        sqlite[f"{self.key_name}.challenge.{user_id}"] = state
        return state

    def del_challenge_state(self, user_id: int):
        key = f"{self.key_name}.challenge.{user_id}"
        if sqlite.get(key):
            del sqlite[key]

    # endregion

    # region Flood State

    def get_flood_state(self) -> dict:
        return sqlite.get(f"{self.key_name}.flood_state", {})

    def set_flood_state(self, state: dict) -> dict:
        sqlite[f"{self.key_name}.flood_state"] = state
        return state

    def del_flood_state(self):
        key = f"{self.key_name}.flood_state"
        if sqlite.get(key):
            del sqlite[key]

    # endregion


@dataclass
class Command:
    user: User
    msg: Message

    # Regex
    alias_rgx = r":alias: (.+)"
    param_rgx = r":param (opt)?\s?(\w+):\s?(.+)"

    # region Helpers (Formatting, User ID)

    @classmethod
    def _generate_markdown(cls):
        self = cls(None, None)  # noqa
        result = [f"版本: v{get_version()}", ""]
        members = inspect.getmembers(self, inspect.iscoroutinefunction)
        members.sort(key=_sort_line_number)
        for name, func in members:
            if name.startswith("_"):
                continue
            result.append(self._extract_docs(func.__name__, func.__doc__ or "", True))
        return "\n".join(result)

    async def _run_command(self):
        command = len(self.msg.parameter) > 0 and self.msg.parameter[0] or cmd_name
        if not (func := self[command]):
            return False, "NOT_FOUND", command
        full_arg_spec = inspect.getfullargspec(func)
        args_len = None if full_arg_spec.varargs else len(full_arg_spec.args)
        cmd_args = self.msg.parameter[1:args_len]
        func_args = []
        for index, arg_type in enumerate(
            tuple(full_arg_spec.annotations.values())
        ):  # Check arg type
            if args_len is None:
                func_args = cmd_args
                break
            try:
                if getattr(arg_type, "__origin__", None) == Union:
                    NoneType = type(None)
                    if (
                        len(arg_type.__args__) != 2
                        or arg_type.__args__[1] is not NoneType
                    ):
                        continue
                    if (
                        len(cmd_args) - 1 > index
                        and not cmd_args[index]
                        or len(cmd_args) - 1 < index
                    ):
                        func_args.append(None)
                        continue
                    arg_type = arg_type.__args__[0]
                func_args.append(arg_type(cmd_args[index]))
            except ValueError:
                return (
                    False,
                    "INVALID_PARAM",
                    tuple(full_arg_spec.annotations.keys())[index],
                )
            except IndexError:  # No more args
                await self.help(command)
                return True, None, None
        try:
            await func(*func_args)
        except Exception as e:
            console.error(
                f"Error when running command {command}: {e}\n{traceback.format_exc()}"
            )
            await self.msg.edit(
                lang("cmd_err_run")
                % (self._get_user_cmd_input(), str(e), traceback.format_exc())
            )
        return True, None, None

    def _get_user_cmd_input(self) -> str:
        return f",{user_cmd_name} {' '.join(self.msg.parameter)}"

    def _extract_docs(self, subcmd_name: str, text: str, markdown: bool = False) -> str:
        extras = []
        if result := re.search(self.param_rgx, text):
            is_optional = (
                f"({italic(lang('cmd_param_optional'))} ) " if result[1] else ""
            )
            extras.extend(
                (
                    f"{lang('cmd_param')}:",
                    f"{is_optional}{code(result[2].lstrip('_'))} - {result[3]}",
                )
            )

            text = re.sub(self.param_rgx, "", text)
        if result := re.search(self.alias_rgx, text):
            alias = result[1].replace(" ", "").split(",")
            alia_text = ", ".join(code(a) for a in alias)
            extras.append(f"{lang('cmd_alias')}: {alia_text}")
            text = re.sub(self.alias_rgx, "", text)
        len(extras) and extras.insert(0, "")
        cmd_display = code(
            f",{cmd_name} {self._get_cmd_with_param(subcmd_name)}".strip()
        )
        if markdown:
            result = [
                "<details>",
                f"<summary>{self._get_cmd_with_param(subcmd_name, markdown) or code(cmd_name)} · {re.search(r'(.+)', self[subcmd_name].__doc__ or '')[1].strip()}</summary>",
                "\n>\n",
                f"用法：{cmd_display}",
                "",
                re.sub(r" {4,}", "", text)
                .replace("{cmd_name}", cmd_name)
                .strip()
                .replace("\n", "\n\n"),
                "\n\n".join(extras),
                "",
                "---",
                "</details>",
            ]
            return "\n".join(result)
        return "\n".join(
            [
                cmd_display,
                re.sub(r" {4,}", "", text).replace("{cmd_name}", cmd_name).strip(),
            ]
            + extras
        )

    def _get_cmd_with_param(self, subcmd_name: str, markdown: bool = False) -> str:
        if subcmd_name == cmd_name:
            return ""
        msg = subcmd_name
        if result := re.search(self.param_rgx, getattr(self, msg).__doc__ or ""):
            if markdown:
                msg = f"<code>{msg}</code>"
            param = result[2].lstrip("_")
            msg += f" [{param}]" if result[1] else html.escape(f" <{param}>")
        elif markdown:
            msg = f"<code>{msg}</code>"
        return msg

    def _get_mapped_alias(self, alias_name: str, ret_type: str):
        # Get alias function
        for name, func in inspect.getmembers(self, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue
            if (
                result := re.search(self.alias_rgx, func.__doc__ or "")
            ) and alias_name in result[1].replace(" ", "").split(","):
                return func if ret_type == "func" else name

    async def _display_value(
        self,
        *,
        key: Optional[str] = None,
        display_text: str,
        sub_cmd: str,
        value_type: str,
    ):
        text = [
            display_text,
            "",
            lang("tip_edit")
            % html.escape(f",{user_cmd_name} {sub_cmd} <{lang(value_type)}>"),
        ]
        key and text.insert(0, f'{lang(f"{key}_curr_rule")}:')
        return await self._edit("\n".join(text))

    # Set On / Off Boolean
    async def _set_toggle(self, key: str, toggle: str, *, reverse: bool = False):
        if (toggle := toggle.lower()[0]) not in ("y", "n", "t", "f", "1", "0") and (
            toggle := toggle.lower()
        ) not in ("on", "off"):
            return await self.help(key)
        toggle = toggle in ("y", "t", "1", "on")
        not reverse and (toggle and setting.set(key, True) or setting.delete(key))
        reverse and (toggle and setting.delete(key) or setting.set(key, False))
        await self._edit(lang(f"{key}_set") % lang("enabled" if toggle else "disabled"))

    
    
    async def _get_user_id(self, user_id_str: Union[str, int]) -> Optional[int]:
        """
        解析用户ID。内部包含一个调试开关来处理机器人ID。
        """
        # --- 调试开关 ---
        # 设置为 True 来允许管理指令 (check, delete 等) 操作机器人ID。
        # 调试结束后，请务必将其改回 False！
        DEBUG_ALLOW_BOTS = False  # <--- 你只需要在这里切换 True / False

        target_user_id = None
        
        # 1. 解析传入的 ID 或从回复/私聊中获取 ID
        if user_id_str:
            try:
                target_user_id = int(user_id_str)
            except (ValueError, TypeError):
                try:
                    entity = await bot.get_entity(user_id_str)
                    target_user_id = entity.id
                except (ValueError, PeerIdInvalidError, TypeError):
                    return None
        else:
            reply_msg = await self.msg.get_reply_message()
            if reply_msg:
                target_user_id = reply_msg.sender_id
            elif self.msg.is_private:
                target_user_id = self.msg.chat_id

        if not target_user_id:
            return None

        # 2. 验证 ID 的有效性
        try:
            user = await bot.get_entity(target_user_id)
            
            # 必须是用户类型，不能是频道或群组
            if not isinstance(user, User):
                return None
            
            is_bot = user.bot
            is_verified = user.verified
            is_deleted = getattr(user, 'deleted', False)

            # 使用开关来控制机器人检查
            # 如果调试开关是关闭的，并且对方是机器人，则返回无效
            if not DEBUG_ALLOW_BOTS and is_bot:
                return None

            # 认证用户和已删除账户总是被认为是无效的（对于添加到验证列表等操作）
            if is_verified or is_deleted:
                return None
                    
        except (ValueError, PeerIdInvalidError, TypeError):
            return None
            
        return user.id


    # Set Black / White List
    async def _set_list(self, _type: str, array: str):
        if not array:
            return await self._display_value(
                key=_type,
                display_text=code(setting.get(_type, lang("none"))),
                sub_cmd=f"{_type[0]}l",
                value_type="vocab_array",
            )
        if array.startswith("-c"):
            setting.delete(_type)
            return await self._edit(lang(f"{_type}_reset"))
        setting.set(_type, array.replace(" ", "").split(","))
        await self._edit(lang(f"{_type}_set"))

    # endregion

    async def _edit(self, msg: str):
        text = "\n\n".join((f">>> {code(self._get_user_cmd_input())}", msg))
        return await self.msg.edit(
            text, parse_mode='html', link_preview=False
        )

    def __getitem__(self, cmd: str) -> Optional[Callable]:
        # Get subcommand function
        if func := getattr(self, cmd, None):
            return func
        # Check for alias
        if func := self._get_mapped_alias(cmd, "func"):
            return func
        return  # Not found

    def get(self, cmd: str, default=None):
        return self[cmd] or default

    async def pmcaptcha(self):
        """查询当前用户的验证状态"""
        if not (user_id := await self._get_user_id(self.msg.chat.id)):
            return await self._edit(lang("invalid_user_id"))
        await self._edit(
            lang(f'verify_{"" if setting.is_verified(user_id) else "un"}verified')
        )
        await asyncio.sleep(5)
        await self.msg.delete()

    async def version(self):
        """查看 <code>PMCaptcha</code> 当前版本

        :alias: v, ver
        """
        await self._edit(f"{lang('curr_version') % get_version()}")

    async def help(self, command: Optional[str], search_str: Optional[str] = None):
        """显示指令帮助信息，使用 <code>,{cmd_name} search [搜索内容]</code> 进行文档、指令(和别名)搜索

        :param opt command: 命令名称
        :param opt search_str: 搜索的文字，只有 <code>command</code> 为 <code>search</code> 时有效
        :alias: h
        """
        help_msg = [f"{code('PMCaptcha')} {lang('cmd_list')}:", ""]
        footer = [
            italic(lang("cmd_detail")),
            "",
            f"{lang('priority')}:\n{' > '.join(Rule._get_rules_priority())}",
            "",
            f"遇到任何问题请先 {code(',apt update')} 、 {code(',restart')} 后复现再反馈",
            (
                f"👉 {gen_link('捐赠网址', 'https://afdian.net/@xtaodada')} "
                f"{gen_link('捐赠说明', 'https://t.me/PagerMaid_Modify/121')} "
                f"(v{get_version()})"
            ),
        ]
        if command == "search":  # Search for commands or docs
            if not search_str:
                return await self.help("h")
            search_str = search_str.lower()
            search_results = [lang("cmd_search_result") % search_str]
            have_cmd = False
            have_doc = False
            for name, func in inspect.getmembers(self, inspect.iscoroutinefunction):
                if name.startswith("_"):
                    continue
                # Search for docs
                docs = func.__doc__ or ""
                if docs.lower().find(search_str) != -1:
                    not have_doc and search_results.append(
                        f"{lang('cmd_search_docs')}:"
                    )
                    have_doc = True
                    search_results.append(self._extract_docs(func.__name__, docs))
                # Search for commands
                if name.find(search_str) != -1:
                    not have_cmd and search_results.append(
                        f"{lang('cmd_search_cmds')}:"
                    )
                    have_cmd = True
                    search_results.append(
                        f"""{code(f"- {code(self._get_cmd_with_param(name))}".strip())}\n· {re.search('(.+)', docs)[1].strip()}\n"""
                    )
                elif result := re.search(self.alias_rgx, docs):
                    if search_str not in result[1].replace(" ", "").split(","):
                        continue
                    not have_cmd and search_results.append(
                        f"{lang('cmd_search_cmds')}:"
                    )
                    have_cmd = True
                    search_results.append(
                        f"""{f"* {code(search_str)} -> {code(self._get_cmd_with_param(func.__name__))}".strip()}\n· {re.search('(.+)', docs)[1].strip()}\n"""
                    )
            len(search_results) == 1 and search_results.append(
                italic(lang("cmd_search_none"))
            )
            return await self._edit("\n\n".join(search_results))
        elif command:  # Single command help
            func = getattr(self, command, self._get_mapped_alias(command, "func"))
            return await (
                self._edit(self._extract_docs(func.__name__, func.__doc__ or ""))
                if func
                else self._edit(f"{lang('cmd_not_found')}: {code(command)}")
            )
        members = inspect.getmembers(self, inspect.iscoroutinefunction)
        members.sort(key=_sort_line_number)
        for name, func in members:
            if name.startswith("_"):
                continue
            help_msg.append(
                (
                    code(f",{user_cmd_name} {self._get_cmd_with_param(name)}".strip())
                    + f"\n· {re.search(r'(.+)', func.__doc__ or '')[1].strip()}\n"
                )
            )
        await self._edit("\n".join(help_msg + footer))

    # region Checking User / Manual update

    async def check(self, _id: Optional[str]):
        """查询指定用户验证状态，对该信息回复或者输入用户 ID，如未指定为当前私聊用户 ID

        :param opt _id: 用户 ID
        """
        if not (user_id := await self._get_user_id(_id)):
            return await self._edit(lang("invalid_user_id"))
        await self._edit(
            lang(f"user_{'' if setting.is_verified(user_id) else 'un'}verified")
            % user_id
        )

    async def add(self, _id: Optional[str]):
        """将 ID 加入已验证，对该信息回复或者输入用户 ID，如未指定为当前私聊用户 ID

        :param opt _id: 用户 ID
        """
        if not (user_id := await self._get_user_id(_id)):
            return await self._edit(lang("invalid_user_id"))
        if captcha := curr_captcha.get(
            user_id
        ):  # This user is currently in challenge state
            await captcha.action(True)
            if curr_captcha.get(user_id):
                del curr_captcha[user_id]
            result = True
        else:
            result = setting.whitelist.add_id(user_id)
            await CaptchaTask.archive(user_id, un_archive=True)
        await self._edit(
            lang(f"add_whitelist_{'success' if result else 'failed'}") % user_id
        )

    async def delete(self, _id: Optional[str]):
        """移除 ID 验证记录，对该信息回复或者输入用户 ID，如未指定为当前私聊用户 ID

        :param opt _id: 用户 ID
        :alias: del
        """
        if not (user_id := await self._get_user_id(_id)):
            return await self._edit(lang("invalid_user_id"))
        text = lang(
            f"remove_verify_log_{'success' if setting.whitelist.del_id(user_id) else 'not_found'}"
        )
        await self._edit(text % user_id)
        
    async def list_verified(self):
        """列出所有已通过验证的用户 ID
        
        :alias: list, ls
        """
        verified_ids = setting.whitelist.get_subs()

        if not verified_ids:
            return await self._edit("✅ **已验证用户列表为空**")

        output_lines = [
            "✅ **已通过验证的用户 ID 列表**:",
            ""
        ]
        
        for user_id in verified_ids:
            # Pagermaid 的 Sub 类返回的是字符串，我们需要确保它们是整数
            output_lines.append(f"• `{int(user_id)}`")
            
        max_display = 100
        total_users = len(verified_ids)
        if total_users > max_display:
            output_lines = output_lines[:max_display+2]
            output_lines.append(f"\n... (总共 {total_users} 个用户, 仅显示前 {max_display} 个)")

        await self._edit("\n".join(output_lines))

    # endregion

    async def unstuck(self, _id: Optional[str]):
        """解除一个用户的验证状态，通常用于解除卡死的验证状态
        使用：对该信息回复或者输入用户 ID，如未指定为当前私聊用户 ID

        :param opt _id: 用户 ID
        """
        if not (user_id := await self._get_user_id(_id)):
            return await self._edit(lang("invalid_user_id"))
        captcha = None
        if (state := setting.get_challenge_state(user_id)) or (
            captcha := curr_captcha.get(user_id)
        ):
            await CaptchaTask.archive(user_id, un_archive=True)
            try:
                (
                    captcha and captcha.type or state.get("type", "math")
                ) == "img" and await exec_api(bot(UnblockRequest(id=user_id)))
            except Exception as e:
                console.error(
                    f"Error when unblocking user {user_id}: {e}\n{traceback.format_exc()}"
                )
            if captcha := curr_captcha.get(user_id):
                captcha.timer_task and captcha.timer_task.cancel()
                del curr_captcha[user_id]
            state and setting.del_challenge_state(user_id)
            return await self._edit(lang("unstuck_success") % user_id)
        await self._edit(lang("not_stuck") % user_id)

    async def welcome(self, *message: Optional[str]):
        """查看或设置验证通过时发送的消息
        使用 <code>,{cmd_name} welcome -c</code> 可恢复默认规则

        :param opt message: 消息内容
        :alias: wel
        """
        if not message:
            return await self._display_value(
                key="welcome",
                display_text=code(setting.get("welcome", lang("none"))),
                sub_cmd="wel",
                value_type="vocab_msg",
            )
        message = " ".join(message)
        if message.startswith("-c"):
            setting.delete("welcome")
            return await self._edit(lang("welcome_reset"))
        setting.set("welcome", message)
        await self._edit(lang("welcome_set"))

    async def whitelist(self, array: Optional[str]):
        """查看或设置关键词白名单列表（英文逗号分隔）
        使用 <code>,{cmd_name} whitelist -c</code> 可清空列表

        :param opt array: 白名单列表 (英文逗号分隔)
        :alias: wl, whl
        """
        return await self._set_list("whitelist", array)

    async def blacklist(self, array: Optional[str]):
        """查看或设置关键词黑名单列表 (英文逗号分隔)
        使用 <code>,{cmd_name} blacklist -c</code> 可清空列表

        :param opt array: 黑名单列表 (英文逗号分隔)
        :alias: bl
        """
        return await self._set_list("blacklist", array)

    async def timeout(self, seconds: Optional[int], _type: Optional[str]):
        """查看或设置超时时间，默认为 <code>30</code> 秒、图像模式为 <code>5</code> 分钟
        使用 <code>,{cmd_name} wait off</code> 可关闭验证时间限制

        有关验证超时的默认选项：
        - <code>math</code> | <code>30</code> 秒
        - <code>img</code> | <code>5</code> 分钟
        - <code>sticker</code> | <code>30</code> 秒

        在图像模式中，此超时时间会于用户最后活跃而重置，
        建议数值设置大一点让机器人有一个时间可以处理后端操作

        :param opt seconds: 超时时间，单位秒
        :param opt _type: 验证类型，默认为当前类型
        :alias: wait
        """
        if _type and _type not in ("math", "img", "sticker"):
            return await self.help("wait")
        captcha_type: str = _type or setting.get("type", "math")
        key_name: str = {
            "sticker": "sticker_timeout",
            "img": "img_timeout",
            "math": "timeout",
        }.get(captcha_type)
        default_timeout_time: int = {"sticker": 30, "img": 300, "math": 30}.get(
            captcha_type
        )
        if seconds is None:
            return await self._display_value(
                display_text=lang("timeout_curr_rule")
                % int(setting.get(key_name, default_timeout_time)),
                sub_cmd="wait",
                value_type="vocab_int",
            )
        elif seconds == "off":
            setting.delete(key_name)
            return await self._edit(lang("timeout_off"))
        if seconds < 0:
            return await self._edit(lang("invalid_param"))
        setting.set(key_name, seconds)
        await self._edit(lang("timeout_set") % seconds)

    async def disable_pm(self, toggle: Optional[str]):
        """启用 / 禁止陌生人私聊，默认为 <code>关闭</code> （允许私聊）
        此功能会放行联系人和白名单(<i>已通过验证</i>)用户
        您可以使用 <code>,{cmd_name} add</code> 将用户加入白名单

        :param opt toggle: 开关 (y / n)
        :alias: disablepm, disable
        """
        if not toggle:
            return await self._display_value(
                display_text=lang("disable_pm_curr_rule")
                % lang("enabled" if setting.get("disable") else "disabled"),
                sub_cmd="disable_pm",
                value_type="vocab_bool",
            )
        await self._set_toggle("disable", toggle)

    async def stats(self, arg: Optional[str]):
        """查看验证统计
        使用 <code>,{cmd_name} stats -c</code> 重置数据

        :param opt arg: 参数 (reset)
        """
        if not arg:
            data = (
                setting.get("pass", 0) + setting.get("banned", 0),
                setting.get("pass", 0),
                setting.get("banned", 0),
                len(curr_captcha) + len(setting.pending_challenge_list.get_subs()),
                len(setting.pending_ban_list.get_subs()),
                setting.get("flooded", 0),
            )
            text = f"{code('PMCaptcha')} {lang('stats_display') % data}"
            if the_world_eye.triggered:
                text += f"\n\n{lang('stats_flooding') % len(the_world_eye.user_ids)}"
            await self.msg.edit(text, parse_mode='html')
            return
        if arg.startswith("-c"):
            setting.delete("pass").delete("banned").delete("flooded")
            return await self.msg.edit(lang("stats_reset"), parse_mode='html')

    async def action(self, action: Optional[str]):
        """选择验证失败的处理方式，默认为 <code>封禁</code>
        处理方式如下：
        - <code>ban</code> | 封禁
        - <code>delete</code> | 封禁并删除对话
        - <code>none</code> | 不执行任何操作

        :param opt action: 处理方式
        :alias: act
        """
        if not action:
            action = setting.get("action", "ban")
            return await self._display_value(
                key="action",
                display_text=lang(
                    f"action_{action == 'none' and 'set_none' or action}"
                ),
                sub_cmd="act",
                value_type="vocab_action",
            )
        if action not in ("ban", "delete", "none"):
            return await self.help("act")
        action == "ban" and setting.delete("action") or setting.set("action", action)
        if action == "none":
            return await self._edit(lang("action_set_none"))
        return await self._edit(lang("action_set") % lang(f"action_{action}"))

    async def report(self, toggle: Optional[str]):
        """选择验证失败后是否举报该用户，默认为 <code>开启</code>

        :param opt toggle: 开关 (y / n)
        """
        if not toggle:
            return await self._display_value(
                display_text=lang("report_curr_rule")
                % lang("enabled" if setting.get("report", True) else "disabled"),
                sub_cmd="report",
                value_type="vocab_bool",
            )
        await self._set_toggle("report", toggle, reverse=True)

    async def premium(self, action: Optional[str]):
        """选择对 <b>Premium</b> 用户的操作，默认为 <code>不执行任何操作</code>
        处理方式如下：
        - <code>allow</code> | 白名单
        - <code>ban</code> | 封禁
        - <code>only</code> | 只允许
        - <code>none</code> | 不执行任何操作

        :param opt action: 处理方式
        :alias: vip, prem
        """
        if not action:
            return await self._display_value(
                key="premium",
                display_text=lang(f'premium_set_{setting.get("premium", "none")}'),
                sub_cmd="vip",
                value_type="vocab_action",
            )
        if action not in ("allow", "ban", "only", "none"):
            return await self.help("vip")
        action == "none" and setting.delete("action") or setting.set("action", action)
        await self._edit(lang(f"premium_set_{action}"))

    async def groups_in_common(self, count: Optional[int]):
        """设置是否对拥有一定数量的共同群的用户添加白名单
        使用 <code>,{cmd_name} groups -1</code> 重置设置

        :param opt count: 共同群数量
        :alias: group, groups, common
        """
        if not count:
            groups = setting.get("groups_in_common")
            text = lang(
                f"groups_in_common_{'set' if groups is not None else 'disabled'}"
            )
            if groups is not None:
                text = text % groups
            return await self._display_value(
                display_text=text, sub_cmd="groups", value_type="vocab_int"
            )
        if count == -1:
            setting.delete("groups_in_common")
            return await self._edit(lang("groups_in_common_disable"))
        elif count < 0:
            return await self.help("groups_in_common")
        setting.set("groups_in_common", count)
        await self._edit(lang("groups_in_common_set") % count)

    async def chat_history(self, count: Optional[int]):
        """设置对拥有一定数量的聊天记录的用户添加白名单（触发验证的信息不计算在内）
        使用 <code>,{cmd_name} his -1</code> 重置设置

        <b>请注意，由于 <code>Telegram</code> 内部限制，数值过大会导致程序缓慢，请不要设置过大的数值</b>

        :param opt count: 聊天记录数量
        :alias: his, history
        """
        if not count:
            history_count = setting.get("history_count")
            text = lang(
                "chat_history_curr_rule"
                if history_count is not None
                else "chat_history_disabled"
            )
            if history_count is not None:
                text = text % history_count
            return await self._display_value(
                display_text=text, sub_cmd="his", value_type="vocab_bool"
            )
        count < 0 and setting.delete("history_count") or setting.set(
            "history_count", count
        )
        await self._edit(lang("chat_history_curr_rule") % count)

    async def initiative(self, toggle: Optional[str]):
        """设置对主动进行对话的用户添加白名单，默认为 <code>开启</code>

        :param opt toggle: 开关 (y / n)
        """
        if not toggle:
            return await self._display_value(
                display_text=lang("initiative_curr_rule")
                % lang("enabled" if setting.get("initiative", True) else "disabled"),
                sub_cmd="initiative",
                value_type="vocab_bool",
            )
        await self._set_toggle("initiative", toggle, reverse=True)

    async def silent(self, toggle: Optional[str]):
        """减少信息发送，默认为 <code>关闭</code>
        开启后，封禁、验证成功提示（包括欢迎信息）信息将不会发送
        （并不会影响到 <code>log</code> 发送）

        :param opt toggle: 开关 (y / n)
        :alias: quiet
        """
        if not toggle:
            return await self._display_value(
                display_text=lang("silent_curr_rule")
                % lang("enabled" if setting.get("silent") else "disabled"),
                sub_cmd="quiet",
                value_type="vocab_bool",
            )
        await self._set_toggle("silent", toggle)

    async def flood(self, limit: Optional[int]):
        """设置一分钟内超过 <code>n</code> 人开启轰炸检测机制，默认为 <code>5</code> 人
        此机制会在用户被轰炸时启用，持续 <code>5</code> 分钟，假如有用户继续进行私聊计时将会重置

        当轰炸开始时，<code>PMCaptcha</code> 将会启动以下一系列机制
        - 强制开启自动归档（无论是否 <code>Telegram Premium</code> 用户都会尝试开启）
        - 不向用户发送 <code>CAPTCHA</code> 挑战
        - 继上面的机制，记录未发送 <code>CAPTCHA</code> 的用户 ID
        - （用户可选）创建临时频道，并把用户名转移到创建的频道上 【默认关闭】

        轰炸结束后，如果用户名已转移到频道上，将恢复用户名，并删除频道
        并对记录收集机器人发送轰炸的<code>用户数量</code>、<code>轰炸开始时间</code>、<code>轰炸结束时间</code>、<code>轰炸时长</code>
        <i>（由于不存在隐私问题，此操作为强制性）</i>

        请参阅 <code>,{cmd_name} h flood_username</code> 了解更多有关创建临时频道的机制
        请参阅 <code>,{cmd_name} h flood_act</code> 查看轰炸结束后的处理方式

        :param opt limit: 人数限制
        :alias: boom
        """
        if not limit:
            return await self._display_value(
                display_text=lang("flood_curr_rule") % setting.get("flood_limit", 50),
                sub_cmd="flood",
                value_type="vocab_int",
            )
        setting.set("flood_limit", limit)
        await self._edit(lang("flood_curr_rule") % limit)

    async def flood_username(self, toggle: Optional[str]):
        """设置是否在轰炸时启用“转移用户名到临时频道”机制（如有用户名）
        将此机制分开出来的原因是此功能有可能会被抢注用户名<i>(虽然经测试并不会出现此问题)</i>
        但为了以防万一依然分开出来作为一个选项了

        启用后，在轰炸机制开启时，会进行以下操作
        - 创建临时频道
        - （如创建成功）清空用户名，设置用户名为临时频道，并在频道简介设置正在受到轰炸提示
        - （如设置失败）恢复用户名，删除频道

        注意：<b>请预留足够的公开群用户名设置额度，否则将不会设置成功，但同时用户名也不会被清空</b>
        <i>（操作失败虽然会有 log 提醒，但请不要过度依赖 log）</i>

        :param opt toggle: 开关 (y / n)
        :alias: boom_username
        """
        global user_want_set_flood_username
        if not toggle:
            return await self._display_value(
                display_text=lang("flood_username_curr_rule")
                % lang("enabled" if setting.get("flood_username") else "disabled"),
                sub_cmd="flood_username",
                value_type="vocab_bool",
            )
        if toggle in ("y", "t", "1", "on") and not user_want_set_flood_username:
            user_want_set_flood_username = True
            return await self._edit(lang("flood_username_set_confirm"))
        user_want_set_flood_username = None
        await self._set_toggle("flood_username", toggle)

    async def flood_act(self, action: Optional[str]):
        """设置轰炸结束后进行的处理方式，默认为 <code>删除并举报所有轰炸的用户</code>
        可用的处理方式如下：
        - <code>asis</code> | 与验证失败的处理方式一致，但不会进行验证失败通知以及发送<code>log</code>记录
        - <code>delete</code> | 删除并举报所有轰炸的用户（速度最快）
        - <code>captcha</code> | 对每个用户进行 <code>CAPTCHA</code> 挑战
        - <code>none</code> | 不进行任何操作

        :param opt action: 处理方式
        :alias: boom_act
        """
        if not action:
            return await self._display_value(
                display_text=lang("flood_act_curr_rule")
                % lang(f"flood_act_set_{setting.get('flood_act', 'delete')}"),
                sub_cmd="flood_act",
                value_type="vocab_action",
            )
        if action not in ("asis", "captcha", "none", "delete"):
            return await self.help("flood_act")
        action == "none" and setting.delete("flood_act") or setting.set(
            "flood_act", action
        )
        await self._edit(lang(f"flood_act_set_{action}"))

    async def custom_rule(self, *rule: Optional[str]):
        """用户自定义过滤规则，规则返回<code>True</code>为白名单，否则继续执行下面的规则
        使用 <code>,{cmd_name} custom_rule -c</code> 可删除规则

        注意事项：
        - 返回<code>True</code>并不代表添加到白名单，只是停止继续执行规则
        - 规则发送错误默认返回<code>False</code>（继续执行规则），并透过<code>log</code>输出错误信息
        - <b>由于此指令能够直接操作账号，因此请在输入他人给与的规则前先亲自确认是否安全</b>

        可用参数：
        - <code>msg</code> | 触发验证的信息
        - <code>text</code> | 触发验证的信息的文本，永远不为<code>None</code>
        - <code>user</code> | 用户
        - <code>me</code> | 机器人用户（自己）
        - global 数值 (例如: <code>curr_captcha</code>, <code>the_order</code> 等)
        - 注意，可以调用 <code>await 函数</code>

        范例：
        <code class="language-python">text == "BYPASS"</code>

        解释：
        当对方发送的文字为“BYPASS”时，不继续执行规则

        :param rule: 规则
        """
        if not rule:
            return await self._display_value(
                key="custom_rule",
                display_text=code(setting.get("custom_rule", lang("none"))),
                sub_cmd="custom_rule",
                value_type="vocab_rule",
            )
        rule = " ".join(rule)
        if rule.startswith("-c"):
            setting.delete("custom_rule")
            return await self._edit(lang("custom_rule_reset"))
        setting.set("custom_rule", rule)
        await self._edit(lang("custom_rule_set") % rule)

    async def collect_logs(self, toggle: Optional[str]):
        """查看或设置是否允许 <code>PMCaptcha</code> 收集验证错误相关信息以帮助改进
        默认为 <code>开启</code>，收集的信息包括被验证者的信息以及未通过验证的信息记录

        :param opt toggle: 开关 (y / n)
        :alias: collect, log
        """
        if not toggle:
            status = lang(
                "enabled" if setting.get("collect_logs", True) else "disabled"
            )
            return await self._display_value(
                display_text=f"{lang('collect_logs_curr_rule') % status}\n{lang('collect_logs_note')}",
                sub_cmd="log",
                value_type="vocab_bool",
            )
        await self._set_toggle("collect_logs", toggle, reverse=True)

    async def change_type(self, _type: Optional[str]):
        """切换验证码类型，默认为 <code>计算验证</code>
        验证码类型如下：
        - <code>math</code> | 计算验证
        - <code>img</code> | 图像辨识验证
        - <code>sticker</code> | 贴纸验证

        <b>注意：如果图像验证不能使用将回退到计算验证</b>

        :param opt _type: 验证码类型
        :alias: type, typ
        """
        if not _type:
            return await self._display_value(
                display_text=lang("type_curr_rule")
                % lang(f'type_captcha_{setting.get("type", "math")}'),
                sub_cmd="typ",
                value_type="type_param_name",
            )
        if _type not in ("img", "math", "sticker"):
            return await self.help("typ")
        _type == "math" and setting.delete("type") or setting.set("type", _type)
        await self._edit(lang("type_set") % lang(f"type_captcha_{_type}"))

    async def show_settings(self):
        """显示目前所有的设置

        :alias: settings, setting
        """
        settings_text = []
        text_none = bold(lang("none"))
        for key, default in (
            ("whitelist", text_none),
            ("blacklist", text_none),
            ("timeout", 300 if setting.get("type") == "img" else 30),
            ("disable_pm", bold(lang("disabled"))),
            ("action", bold(lang("action_ban"))),
            ("report", bold(lang("enabled"))),
            ("premium", bold(lang("premium_set_none"))),
            ("groups_in_common", text_none),
            ("chat_history", -1),
            ("initiative", bold(lang("enabled"))),
            ("silent", bold(lang("disabled"))),
            ("flood", 5),
            ("flood_username", bold(lang("disabled"))),
            ("flood_act", bold(lang("flood_act_set_delete"))),
            ("collect_logs", bold(lang("enabled"))),
            ("type", bold(lang("type_captcha_math"))),
            ("img_captcha", bold(lang("img_captcha_type_func"))),
            ("img_captcha_retry", 3),
            ("custom_rule", text_none),
            ("welcome", text_none),
        ):
            lang_text = lang(f"{key}_curr_rule")
            # Timeout (rule: timeout, value: [multiple])
            if key == "timeout":
                captcha_type = setting.get("type", "math")
                key: str = {
                    "sticker": "sticker_timeout",
                    "img": "img_timeout",
                    "math": "timeout",
                }.get(captcha_type)
                default: int = {"sticker": 30, "img": 300, "math": 30}.get(captcha_type)
            # Disable (rule: disable_pm, val: disable)
            elif key == "disable_pm":
                key = "disable"
            # Chat History (rule: chat_history, val: history_count)
            elif key == "chat_history":
                key = "history_count"
            # Flood (key: flood, val: flood_limit)
            elif key == "flood":
                key = "flood_limit"
            # Image Type (rule: img_captcha_type, val: img_type)
            elif key == "img_captcha":
                key = "img_type"
            # Image Retry Chance (rule: img_captcha_retry, value: img_max_retry)
            elif key == "img_captcha_retry":
                key = "img_max_retry"
            value = setting.get(key, default)
            if isinstance(value, bool):
                value = bold(lang("enabled" if value else "disabled"))
            elif key == "premium":
                value = "\n" + value
            if lang_text.find("%") != -1:
                lang_text = lang_text % value
            else:
                lang_text += f": {bold(str(value))}"
            settings_text.append(lang_text)
        await self._edit(lang("settings_lists") % "\n".join(settings_text))

    # Config Export / Import

    async def export_settings(self):
        """导出目前 <code>PMCaptcha</code> 的设置
        请注意，此导出并不包括：
        - 封禁人数缓存
        - 白名单
        - 等待验证缓存

        :alias: export, export_setting
        """
        config = sqlite[setting.key_name]
        config["version"] = get_version()
        for key in ("pass", "banned", "flooded"):
            if config.get(key):
                del config[key]
        file = BytesIO(json.dumps(config, indent=4).encode())
        file.name = f"{str_timestamp(int(time.time()))}.pmc-settings.json"
        await bot.send_file("me", file, caption=file.name)
        await self._edit(lang("export_success"))

    async def import_settings(self):
        """导入 <code>PMCaptcha</code> 的设置，对着设置文件回复即可
        请注意，如果导出和导入的版本不一样可能会因为版本兼容问题
        导致有些设置可能会无法导入，届时将会提示

        :alias: import_setting, import
        """
        reply_msg = await self.msg.get_reply_message()
        if not (reply_msg and reply_msg.document):
            return await self.help("import")
        try:
            # noinspection PyUnresolvedReferences
            config_bytes = await reply_msg.download_media(file=bytes)
            config = json.loads(config_bytes)
        except (json.JSONDecodeError, ValueError):
            return await self._edit(lang("import_failed"))
        if config.get("version") != get_version():
            return await self._edit(lang("import_version_mismatch"))
        del config["version"]
        for key, value in config.items():
            setting.set(key, value)
        await self._edit(lang("import_success"))

    # Image Captcha

    async def change_img_type(self, _type: Optional[str]):
        """切换图像辨识使用接口，默认为 <code>funCaptcha</code>
        目前可用的接口：
        - <code>func</code> (<i>ArkLabs funCaptcha</i> )
        - <code>github</code> (<i>GitHub 螺旋星系</i> )
        - <code>rec</code> (<i>Google reCAPTCHA</i> )

        请注意， <code>reCAPTCHA</code> 难度相比前两个<a href="https://t.me/c/1441461877/958395">高出不少</a>，
        因此验证码系统会在尝试过多后提供 <code>funCaptcha</code> 接口让用户选择

        :param opt _type: 验证码类型
        :alias: img_type, img_typ
        """
        if not _type:
            return await self._display_value(
                display_text=lang("type_curr_rule")
                % lang(f'img_captcha_type_{setting.get("img_type", "func")}'),
                sub_cmd="img_typ",
                value_type="type_param_name",
            )
        if _type not in ("func", "github", "rec"):
            return await self.help("img_typ")
        _type == "func" and setting.delete("img_type") or setting.set("img_type", _type)
        await self._edit(lang("type_set") % lang(f"img_captcha_type_{_type}"))

    async def img_retry_chance(self, number: Optional[int]):
        """图形验证码最大可重试次数，默认为 <code>3</code>

        :param opt number: 重试次数
        :alias: img_re
        """
        if number is None:
            return await self._display_value(
                display_text=lang("img_captcha_retry_curr_rule")
                % setting.get("img_max_retry", 3),
                sub_cmd="img_re",
                value_type="vocab_int",
            )
        if number < 0:
            return await self._edit(lang("invalid_param"))
        setting.set("img_max_retry", number)
        await self._edit(lang("img_captcha_retry_set") % number)

    # Web Configure (Sam: I'm not touching this)

    async def web_configure(self, config: Optional[str]):
        """PMCaptcha 网页可视化配置

        :alias: web
        """
        if not config:
            try:
                config = sqlite[setting.key_name]
            except KeyError:
                config = {}
            config["version"] = get_version()
            config["cmd"] = user_cmd_name
            for key in ("pass", "banned", "flooded"):
                if config.get(key):
                    del config[key]
            config = b64encode(json.dumps(config).encode("utf-8")).decode("utf-8")
            await self._edit(f"网页配置链接： https://pmc-config.xtaolabs.com/{config}")
            return
        try:
            nc = json.loads(b64decode(config))
        except Exception:
            await self._edit(lang("import_failed"))
            return
        for i in nc:
            if nc[i] == -1:
                setting.delete(i)
            else:
                setting.set(i, nc[i])
        await self._edit(lang("import_success"))


# region Captcha


@dataclass
class TheOrder:
    """Worker of blocking user (Punishment)"""

    queue = asyncio.Queue()
    task: Optional[asyncio.Task] = None

    def __post_init__(self):
        if pending := setting.pending_ban_list.get_subs():
            console.debug(f"Pending user(s) to ban: {len(pending)}")
            if len(pending) > 0 and not self.task or self.task.done():
                self.task = asyncio.create_task(self.worker())
            for user_id in pending:
                self.queue.put_nowait((user_id, False))

    async def worker(self):
        console.debug("Punishment Worker started")
        while True:
            target = None
            try:
                target, skip_log = await self.queue.get()
                action = setting.get("action", "ban")
                if action in ("ban", "delete"):
                    # Use Telethon's Raw API for blocking
                    if not await exec_api(bot(BlockRequest(id=target))):
                        console.debug(f"Failed to block user {target}")
                    if action == "delete":
                        # Use Telethon's Raw API for deleting history
                        peer = await bot.get_input_entity(target)
                        if not await exec_api(
                            bot(
                                messages.DeleteHistoryRequest(
                                    just_clear=False,
                                    revoke=True, # Telethon often uses revoke=True to delete for everyone
                                    peer=peer,
                                    max_id=0,
                                )
                            )
                        ):
                            console.debug(f"Failed to delete user chat {target}")
                setting.pending_ban_list.del_id(target)
                setting.get_challenge_state(target) and setting.del_challenge_state(
                    target
                )
                setting.set("banned", setting.get("banned", 0) + 1)
                chat_link = gen_link(str(target), f"tg://user?id={target}")
                text = f"[PMCaptcha - The Order] {lang('verify_log_punished')} (Punishment)"
                (
                    not skip_log
                    and action not in ("none", "archive")
                    and await log(text % (chat_link, lang(f"action_{action}")), True)
                )
                (
                    skip_log
                    and console.debug(
                        text
                        % (
                            chat_link,
                            lang(f'action_{action == "none" and "set_none" or action}'),
                        )
                    )
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                await log(
                    f"Error occurred when punishing user: {e}\n{traceback.format_exc()}"
                )
            finally:
                target and self.queue.task_done()

    async def active(self, user_id: int, reason_code: str):
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.worker())
        try:
            not the_world_eye.triggered and not setting.get(
                "silent"
            ) and await bot.send_message(
                user_id,
                "\n\n".join((lang_full(reason_code), lang_full("verify_blocked"))),
            )
        except FloodWaitError:
            pass  # Skip waiting
        finally:
            setting.pending_ban_list.add_id(user_id)
            await self.queue.put((user_id, False))
            console.debug(f"User {user_id} added to ban queue")


@dataclass
class TheWorldEye:
    """Anti-Flooding System"""

    queue = asyncio.Queue()
    watcher: Optional[asyncio.Task] = None
    timer_task: Optional[asyncio.Task] = None

    # Watcher
    last_challenge_time: Optional[int] = None
    level: int = 0

    # Post Init Value
    channel_id: Optional[int] = None
    username: Optional[str] = None
    triggered: bool = False
    start: Optional[int] = None
    update: Optional[int] = None
    end: Optional[int] = None
    user_ids: Optional[list] = field(init=False)
    auto_archive_enabled_default: Optional[bool] = None

    def __post_init__(self):
        self.user_ids = []
        if state := setting.get_flood_state():  # PMCaptcha restarts, flood keeps going
            # Resume last flood state
            now = int(time.time())
            self.triggered = True
            self.channel_id = state.get("channel_id")
            self.username = state.get("username")
            self.start = state.get("start")
            self.update = state.get("update")
            self.user_ids = state.get("user_ids")
            self.auto_archive_enabled_default = state.get(
                "auto_archive_enabled_default"
            )
            self.reset_timer(360 - (now - self.start))
            console.debug("PMCaptcha restarted, flood state resume")
        self.watcher = asyncio.create_task(self.sophitia())

    # region Timer

    async def _flood_timer(self, interval: int):
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
        console.debug("Flood timer ended")
        self.end = int(time.time())
        await self.overload()

    def reset_timer(self, interval: int = 270 + randint(30, 60)):
        if self.timer_task:
            self.timer_task.cancel()
        self.update = int(time.time())
        self.timer_task = asyncio.create_task(self._flood_timer(interval))
        console.debug("Flood timer reset")
        return self

    # endregion

    async def _set_channel_username(self):
        console.debug("Creating temporary channel")
        try:
            channel = await bot(
                functions.channels.CreateChannelRequest(
                    title="PMCaptcha Temporary Channel",
                    about="\n\n".join(
                        (lang("flood_channel_desc", "en"), lang("flood_channel_desc", "zh"))
                    ),
                    megagroup=False
                )
            )
            channel = channel.chats[0]
            console.debug("Temporary channel created")
            self.channel_id = channel.id
        except Exception as e:
            await log(
                f"Failed to create temporary channel: {e}\n{traceback.format_exc()}"
            )
            return False
        console.debug("Moving username to temporary channel")
        try:
            await bot(functions.account.UpdateUsernameRequest(username=""))
        except Exception as e:
            await log(f"Failed to remove username: {e}\n{traceback.format_exc()}")
            return False
        result = False
        try:
            channel_entity = await bot.get_input_entity(self.channel_id)
            await bot(
                UpdateUsernameRequest(
                    channel=channel_entity, username=self.username
                )
            )
            result = True
        except RPCError as e:
            if 'CHANNELS_PUBLIC_TOO_MUCH' in str(e):
                await log(
                    "Failed to move username to temporary channel, too many public channels"
                )
            else:
                await log(
                    f"Failed to set username for channel due to an RPCError: {e}\n{traceback.format_exc()}"
                )
        except Exception as e:
            await log(
                f"Failed to set username for channel: {e}\n{traceback.format_exc()}"
            )
        if not result:
            console.debug("Setting back username")
            try:
                await bot(functions.account.UpdateUsernameRequest(username=self.username))
                await bot(functions.channels.DeleteChannelRequest(channel=channel_entity))
            except Exception as e:
                await log(f"Failed to set username back: {e}\n{traceback.format_exc()}")
            self.username = None
        return result

    async def _restore_username(self):
        if self.channel_id:
            console.debug("Deleting temporary channel")
            try:
                channel_entity = await bot.get_input_entity(self.channel_id)
                await bot(functions.channels.DeleteChannelRequest(channel=channel_entity))
            except Exception as e:
                console.debug(
                    f"Failed to delete temporary channel: {e}\n{traceback.format_exc()}"
                )
        if self.username:
            console.debug("Setting back username")
            try:
                await bot(functions.account.UpdateUsernameRequest(username=self.username))
            except Exception as e:
                await log(f"Failed to set username back: {e}\n{traceback.format_exc()}")
        self.username = self.channel_id = None

    # region State

    def save_state(self):
        setting.set_flood_state(
            {
                "start": self.start,
                "update": self.update,
                "user_ids": self.user_ids,
                "auto_archive_enabled_default": self.auto_archive_enabled_default,
                "username": self.username,
                "channel_id": self.channel_id,
            }
        )

    def update_state(self):
        data = setting.get_flood_state()
        data.update(
            {
                "update": self.update,
                "user_ids": self.user_ids,
            }
        )
        setting.set_flood_state(data)

    @staticmethod
    def del_state():
        setting.del_flood_state()

    # endregion

    # noinspection SpellCheckingInspection
    async def sophitia(self):
        """Watches the private message chat (World)"""
        console.debug("Flood Watcher started")
        while True:
            user_id = None
            try:
                (user_id,) = await self.queue.get()
                if self.triggered:  # Continues flooding, add to list and reset timer
                    self.reset_timer()
                    self.user_ids.append(user_id)
                    console.debug(f"User {user_id} added to flood list")
                    self.update_state()
                    continue
                now = int(time.time())
                if self.last_challenge_time and now - self.last_challenge_time < 60:
                    # A user is challenged less than a min
                    self.level += 1
                elif (
                    not self.last_challenge_time or now - self.last_challenge_time > 60
                ):
                    self.level = 1
                self.last_challenge_time = now
                if self.level >= setting.get("flood_limit", 5):
                    console.warn(f"Flooding detected: {self.level} reached in 1 min")
                    self.triggered = True
                    self.start = self.update = now
                    self.reset_timer()
                    await self.synchronize()
            except asyncio.CancelledError:
                break
            except Exception as e:
                await log(
                    f"Error occurred in flood watcher: {e}\n{traceback.format_exc()}"
                )
            finally:
                user_id and self.queue.task_done()

    async def add_synchronize(self, user_id: int):
        await self.queue.put((user_id,))

    async def synchronize(self):
        """Triggered when flood starts (Iris has started synchronizing people)"""
        # Force enable auto archive to reduce api flood
        current_settings: GlobalPrivacySettings = await bot(GetGlobalPrivacySettingsRequest())
        self.auto_archive_enabled_default = (
            current_settings.archive_and_mute_new_noncontact_peers
        )
        console.debug("Enabling auto archive")
        try:
            await bot(
                SetGlobalPrivacySettingsRequest(
                    settings=GlobalPrivacySettings(
                        archive_and_mute_new_noncontact_peers=True
                    )
                )
            )
            console.debug("Auto archive enabled")
        except Exception as e:
            # Telethon doesn't have a specific AutoarchiveNotAvailable error, it will likely be a generic RPCError
            # So we catch the generic error and log it
            console.warn(
                f"Could not enable auto archive (this may be normal for non-premium accounts): {e}"
            )

        if setting.get("flood_username") and bot.me.username:
            self.username = bot.me.username
            console.debug("Moving username to temporary channel")
            if not await self._set_channel_username():
                self.username = None
        # Save state
        self.save_state()

    async def overload(self):
        """Executed after flood ends (Nine has performed load action)"""
        console.info(
            f"Flood ended, {len(self.user_ids)} users were affected, duration: {self.end - self.start}s"
        )
        flood_act = setting.get("flood_act", "delete")
        user_ids, start, end, duration = (
            self.user_ids.copy(),
            self.start,
            self.end,
            self.update - self.start,
        )
        # Reset now so it can handle next flood in time
        rule_lock.locked() and rule_lock.release()
        await rule_lock.acquire()  # Don't process rule until flood state is reset
        self.triggered = False
        self.user_ids.clear()
        self.del_state()
        self.start = self.end = self.update = None
        if self.channel_id or self.username:
            console.debug("Changing back username")
            await self._restore_username()
        try:
            await bot.send_message(
                log_collect_bot,
                "\n".join(
                    (
                        "💣 检测到私聊轰炸",
                        f"设置限制: {code(setting.get('flood_limit', 5))}",
                        f"用户数量: {code(str(len(user_ids)))}",
                        f"开始时间: {code(str_timestamp(start))}",
                        f"结束时间: {code(str_timestamp(end))}",
                        f"轰炸时长: {code(str(duration))} 秒",
                    )
                ),
            )
        except Exception as e:
            console.debug(f"Failed to send flood log: {e}\n{traceback.format_exc()}")
        if not self.auto_archive_enabled_default:  # Restore auto archive setting
            try:
                await bot(
                    SetGlobalPrivacySettingsRequest(
                        settings=GlobalPrivacySettings(
                            archive_and_mute_new_noncontact_peers=False
                        )
                    )
                )
                console.debug("Auto archive disabled")
            except Exception as e:
                console.debug(
                    f"Failed to disable auto archive: {e}\n{traceback.format_exc()}"
                )
        rule_lock.release()  # Let rule processing continue
        setting.set("banned", setting.get("banned", 0) + len(user_ids))
        setting.set("flooded", setting.get("flooded", 0) + 1)
        console.debug(f"Doing flood action: {flood_act}")
        if flood_act == "asis":
            if not the_order.task or the_order.task.done():
                the_order.task = asyncio.create_task(the_order.worker())
            for user_id in user_ids:
                setting.pending_ban_list.add_id(user_id)
            for user_id in user_ids:
                await the_order.queue.put((user_id, True))
        elif flood_act == "captcha":
            if not captcha_task.task or captcha_task.task.done():
                captcha_task.task = asyncio.create_task(captcha_task.worker())
            for user_id in user_ids:
                setting.pending_challenge_list.add_id(user_id)
            for user_id in user_ids:
                if curr_captcha.get(user_id) or setting.get_challenge_state(user_id):
                    continue
                await self.queue.put((user_id, None, None, None))
                console.debug(f"User {user_id} added to challenge queue")
        elif flood_act == "delete":
            console.debug(f"Delete and reporting {len(user_ids)} users")
            for user_id in user_ids:
                peer = await bot.get_input_entity(user_id)
                await exec_api(bot(messages.ReportSpamRequest(peer=peer)))
                await exec_api(
                    bot(
                        messages.DeleteHistoryRequest(
                            just_clear=False, revoke=True, peer=peer, max_id=0
                        )
                    )
                )
        console.debug("Flood action done")


@dataclass
class CaptchaTask:
    """A class to start, resume and verify the captcha challenge"""

    queue = asyncio.Queue()
    task: Optional[asyncio.Task] = None

    def __post_init__(self):
        if pending := setting.pending_challenge_list.get_subs():
            console.debug(f"Pending user(s) to challenge: {len(pending)}")
            if len(pending) > 0 and not self.task or self.task.done():
                self.task = asyncio.create_task(self.worker())
            for user_id in pending:
                self.queue.put_nowait((user_id, None, None, None))

    @staticmethod
    async def archive(user_id: int, *, un_archive: bool = False):
        # This is a complex operation in Telethon, requiring Raw API
        try:
            peer = await bot.get_input_entity(user_id)
            # Mute/Unmute
            notify_setting = InputPeerNotifySettings(
                mute_until=None if un_archive else 2**31 - 1,
                show_previews=un_archive,
                silent=not un_archive,
            )
            await exec_api(
                bot(
                    UpdateNotifySettingsRequest(
                        peer=InputNotifyPeer(peer=peer), settings=notify_setting
                    )
                )
            )
            # Archive/Unarchive
            await exec_api(
                bot(
                    EditPeerFoldersRequest(
                        folder_peers=[InputFolderPeer(peer=peer, folder_id=0 if un_archive else 1)]
                    )
                )
            )
        except Exception as e:
            console.error(f"Failed to archive/unarchive chat {user_id}: {e}")

    @staticmethod
    async def get_user_settings(user_id: int) -> (bool, bool):
        can_report = True
        auto_archived = False
        try:
            peer = await bot.get_input_entity(user_id)
            if peer_settings := await exec_api(
                bot(messages.GetPeerSettingsRequest(peer=peer))
            ):
                can_report = peer_settings.settings.report_spam
                auto_archived = peer_settings.settings.autoarchived
            else:
                console.debug(f"GetPeerSettings failed for {user_id}")
        except Exception:
            console.debug(f"GetPeerSettings failed for {user_id}")
        return can_report, auto_archived

    async def worker(self):
        console.debug("Captcha Challenge Worker started")
        while True:
            user_id: Optional[int] = None
            try:
                user_id, msg, can_report, auto_archived = await self.queue.get()
                user = msg.sender if msg else await bot.get_entity(user_id)
                if can_report is None or auto_archived is None:
                    can_report, auto_archived = await self.get_user_settings(user_id)
                if (
                    last_captcha := setting.get_challenge_state(user_id)
                ) and not curr_captcha.get(user_id):
                    # Resume last captcha challenge
                    if last_captcha["type"] not in captcha_challenges:
                        console.info(
                            "Failed to resume last captcha challenge: "
                            f"Unknown challenge type {last_captcha['type']}"
                        )
                        continue
                    await captcha_challenges[last_captcha["type"]].resume(
                        user=user, msg=msg, state=last_captcha
                    )
                    continue
                # Start a captcha challenge
                await self.archive(user_id)
                captcha = captcha_challenges.get(
                    setting.get("type", "math"), MathChallenge
                )(user, can_report)
                captcha.log_msg(msg.text or None)
                captcha = await captcha.start() or captcha
                curr_captcha[user_id] = captcha
                setting.pending_challenge_list.del_id(user_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await log(
                    f"Error occurred when challenging user: {e}\n{traceback.format_exc()}"
                )
            finally:
                user_id and self.queue.task_done()

    async def add(
        self,
        user_id: int,
        msg: Optional[Message],
        can_report: Optional[bool],
        auto_archived: Optional[bool],
    ):
        await the_world_eye.add_synchronize(user_id)
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.worker())
        if not (
            setting.pending_challenge_list.check_id(user_id)
            or curr_captcha.get(user_id)
            or setting.get_challenge_state(user_id)
        ):
            setting.pending_challenge_list.add_id(user_id)
            self.queue.put_nowait((user_id, msg, can_report, auto_archived))
            console.debug(f"User {user_id} added to challenge queue")


@dataclass
class CaptchaChallenge:
    type: str
    user: User
    input: bool
    logs: List[str] = field(init=False, default_factory=list)
    captcha_write_lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    # User Settings
    can_report: bool = True

    # Post Init Value
    captcha_start: int = 0
    captcha_end: int = 0
    challenge_msg_ids: Optional[List[int]] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None

    # region Logging

    def log_msg(self, msg: Optional[str]):
        if isinstance(msg, str) and not msg.strip():
            return
        self.logs.append(isinstance(msg, str) and msg.strip() or msg)

    async def send_log(self, ban_code: Optional[str] = None):
        if not setting.get("collect_logs", True):
            return
        user = self.user
        log_file = BytesIO(json.dumps(self.logs, indent=4).encode())
        log_file.name = f"{user.id}_{self.captcha_start}.json"
        caption = [
            f"FROM: {code(str(bot.me.id))}",
            f"UID: {code(str(user.id))}"
            + (f" @{user.username}" if self.user.username else ""),
            f"Mention: {gen_link(str(user.id), f'tg://user?id={user.id}')}",
        ]
        user_full_name = []
        user.first_name and user_full_name.append(user.first_name)
        user.last_name and user_full_name.append(user.last_name)
        if user_full_name:
            caption.append(f"Name: {code(' '.join(user_full_name))}")
        elif getattr(user, 'deleted', False):
            caption.append(f"Name: {bold('Deleted Account')}")

        tags = []
        user.scam and tags.append(code("Scam"))
        user.fake and tags.append(code("Fake"))
        user.premium and tags.append(code("Premium"))
        if tags:
            caption.append(f"Tags: {', '.join(tags)}")

        user.lang_code and caption.append(f"Language: {code(user.lang_code)}")
        user.dc_id and caption.append(f"DC: {code(str(user.dc_id))}")
        user.phone and caption.append(f"Phone: {code(user.phone)}")
        self.type and caption.append(f"Type: {code(self.type)}")
        self.can_report and setting.get("report", True) and caption.append(
            f"Spam Reported: {code('Yes')}"
        )
        ban_code and caption.append(f"Block Reason: {code(ban_code)}")
        self.captcha_start and caption.append(f"Start: {code(str(self.captcha_start))}")
        self.captcha_end and caption.append(f"End: {code(str(self.captcha_end))}")
        (
            self.captcha_start
            and self.captcha_end
            and caption.append(
                f"Duration: {code(str(self.captcha_end - self.captcha_start))}s"
            )
        )
        await CaptchaTask.archive(log_collect_bot)
        await exec_api(bot(UnblockRequest(id=log_collect_bot)))
        if not await exec_api(
            bot.send_file(
                log_collect_bot,
                log_file,
                caption="\n".join(caption),
                parse_mode='html',
            )
        ):
            return await log("Failed to send log")
        await log(f"Log collected from user {user.id}")

    # endregion

    # region State

    def save_state(self, extra: Optional[dict] = None):
        self.captcha_start = self.captcha_start or int(time.time())
        data = {
            "type": self.type,
            "start": self.captcha_start,
            "logs": self.logs,
            "msg_ids": self.challenge_msg_ids,
            "report": self.can_report,
        }
        extra and data.update(extra)
        setting.set_challenge_state(self.user.id, data)

    def update_state(self, changes: Optional[dict] = None):
        data = setting.get_challenge_state(self.user.id)
        changes and data.update(changes)
        setting.set_challenge_state(self.user.id, data)

    def del_state(self):
        setting.del_challenge_state(self.user.id)

    # endregion

    # region Verify Result

    async def _del_challenge_msgs(self):
        try:
            await bot.delete_messages(self.user.id, self.challenge_msg_ids)
        except Exception as e:
            console.error(
                f"Failed to delete challenge messages: {e}\n{traceback.format_exc()}"
            )

    async def _verify_success(self, _):
        setting.whitelist.add_id(self.user.id)
        setting.set("pass", setting.get("pass", 0) + 1)
        chat_link = gen_link(str(self.user.id), f"tg://user?id={self.user.id}")
        await log(
            lang("verify_log_passed") % (chat_link, lang(f"type_captcha_{self.type}"))
        )
        success_msg = setting.get("welcome") or lang_full("verify_passed")
        welcome_msg: Optional[Message] = None
        if setting.get("silent"):
            await self._del_challenge_msgs()
            return await CaptchaTask.archive(self.user.id, un_archive=True)
        try:
            if self.challenge_msg_ids:
                await bot.edit_message(self.user.id, self.challenge_msg_ids[0], success_msg)
        except Exception as e:
            console.error(
                f"Failed to edit welcome message: {e}\n{traceback.format_exc()}"
            )
            try:
                welcome_msg = await bot.send_message(self.user.id, success_msg)
            except Exception as e:
                console.error(
                    f"Failed to send welcome message: {e}\n{traceback.format_exc()}"
                )
        await asyncio.sleep(setting.get("welcome") and 5 or 3)
        await self._del_challenge_msgs()
        welcome_msg and await welcome_msg.delete()
        await CaptchaTask.archive(self.user.id, un_archive=True)

    async def _verify_failed(self, reason_code: str):
        try:
            await self._del_challenge_msgs()
            if self.can_report and setting.get("report", True):
                peer = await bot.get_input_entity(self.user.id)
                await bot(messages.ReportSpamRequest(peer=peer))
        except Exception as e:
            console.debug(
                f"Error occurred when executing verify failed function: {e}\n{traceback.format_exc()}"
            )
        await the_order.active(self.user.id, "verify_failed")
        await self.send_log(reason_code)

    async def action(self, success: bool, reason_code="verify_failed"):
        self.captcha_end = int(time.time())
        self.del_state()
        self.remove_timer()
        await getattr(self, f"_verify_{'success' if success else 'failed'}")(
            reason_code
        )
        console.debug(
            f"User {self.user.id} verify {'success' if success else 'failed'}"
        )

    # endregion

    # region Timer

    async def _challenge_timer(self, timeout: int):
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return
        except Exception as e:
            console.error(
                f"Error occurred when running challenge timer: {e}\n{traceback.format_exc()}"
            )
        async with self.captcha_write_lock:
            console.debug(f"User {self.user.id} verification timed out")
            if curr_captcha.get(self.user.id) is self:
                await self.action(False, "verify_timeout")
                del curr_captcha[self.user.id]

    def reset_timer(self, timeout: Optional[int] = None):
        self.timer_task and self.timer_task.cancel()
        timeout = (
            timeout is not None
            and timeout
            or setting.get(
                f"{self.type == 'img' and 'img_' or ''}timeout",
                self.type == "img" and 300 or 30,
            )
        )
        if timeout > 0:
            self.timer_task = asyncio.create_task(self._challenge_timer(timeout))
        console.debug(f"User {self.user.id} verification timer reset")
        return self

    def remove_timer(self):
        if task := self.timer_task:
            task.cancel()
        return self

    # endregion

    @classmethod
    async def resume(cls, *, user: User, msg: Optional[Message] = None, state: dict):
        console.debug(f"User {user.id} resumed captcha challenge {state['type']}")

    async def start(self):
        console.debug(f"User {self.user.id} started {self.type} captcha challenge")


class MathChallenge(CaptchaChallenge):
    answer: int

    def __init__(self, user: User, can_report: bool):
        super().__init__("math", user, True, can_report)

    @classmethod
    async def resume(cls, *, user: User, msg: Optional[Message] = None, state: dict):
        captcha = cls(user, state.get("report", True))
        captcha.captcha_start = state["start"]
        captcha.logs = state["logs"]
        captcha.challenge_msg_ids = (
            [state["msg_id"]] if state.get("msg_id") else state.get("msg_ids", [])
        )

        captcha.answer = state["answer"]
        if (timeout := setting.get("timeout", 30)) > 0:
            time_passed = int(time.time()) - int(state["start"])
            if time_passed > timeout:
                # Timeout
                return await captcha.action(False)
            if msg:  # Verify result
                await captcha.verify(msg.text or "")
            else:  # Restore timer
                captcha.reset_timer(timeout - time_passed)
        await super(MathChallenge, captcha).resume(user=user, msg=msg, state=state)

    async def start(self, previous_msg_id: Optional[int] = None):
        if self.captcha_write_lock.locked():
            return
        async with self.captcha_write_lock:
            import random

            first_value, second_value = random.randint(1, 10), random.randint(1, 10)
            timeout = setting.get("timeout", 30)
            operator = random.choice(("+", "-", "*"))
            expression = f"{first_value} {operator} {second_value}"
            text_to_send = "\n".join(
                (
                    lang_full("verify_challenge"),
                    "",
                    code(f"{expression} = ?"),
                    "",
                    lang_full(
                        "verify_challenge_timed", timeout if timeout > 0 else ""
                    ),
                )
            )

            if previous_msg_id:
                challenge_msg = await exec_api(
                    bot.edit_message(self.user.id, previous_msg_id, text_to_send, parse_mode='html')
                )
            else:
                challenge_msg = await exec_api(
                    bot.send_message(self.user.id, text_to_send, parse_mode='html')
                )

            if not challenge_msg:
                return await log(
                    f"Failed to send math captcha challenge to {self.user.id}"
                )
            self.challenge_msg_ids = [challenge_msg.id]
            self.answer = eval(expression)
            self.save_state({"answer": self.answer})
            self.reset_timer(timeout)
            await super(MathChallenge, self).start()

    async def verify(self, answer: str):
        if self.captcha_write_lock.locked():
            return
        async with self.captcha_write_lock:
            try:
                user_answer = int("".join(re.findall(r"\d+", answer)))
                if "-" in answer:
                    user_answer = -user_answer
            except (ValueError, TypeError):
                return await the_order.active(self.user.id, "verify_failed")
        await self.action(user_answer == self.answer)
        return user_answer == self.answer


class ImageChallenge(CaptchaChallenge):
    try_count: int

    def __init__(self, user: User, can_report: bool):
        super().__init__("img", user, False, can_report)
        self.try_count = 0

    @classmethod
    async def resume(cls, *, user: User, msg: Optional[Message] = None, state: dict):
        captcha = cls(user, state["report"])
        captcha.captcha_start = state["start"]
        captcha.logs = state["logs"]
        captcha.challenge_msg_ids = (
            [state["msg_id"]] if state.get("msg_id") else state.get("msg_ids", [])
        )

        captcha.try_count = state["try_count"]
        if captcha.try_count >= setting.get("img_max_retry", 3):
            return await captcha.action(False)
        if (timeout := setting.get("img_timeout", 300)) > 0:  # Restore timer
            time_passed = int(time.time()) - int(state["last_active"])
            if time_passed > timeout:
                # Timeout
                return await captcha.action(False)
            captcha.reset_timer(timeout - time_passed)
        curr_captcha[user.id] = captcha
        await super(ImageChallenge, captcha).resume(user=user, msg=msg, state=state)

    async def start(self):
        if self.captcha_write_lock.locked():
            return
        async with self.captcha_write_lock:
            while True:
                try:
                    results = await bot.inline_query(
                        img_captcha_bot, setting.get("img_type", "func")
                    )
                    if not results:
                        console.debug(
                            f"Failed to get captcha results from {img_captcha_bot}, fallback"
                        )
                        break  # Fallback

                    # From now on, wait for bot result
                    timeout = setting.get("timeout", 300)
                    challenge_msg = await exec_api(
                        bot.send_message(
                            self.user.id,
                            "\n".join(
                                (
                                    lang_full("verify_challenge"),
                                    "",
                                    code(lang_full("verify_complete_image")),
                                    "",
                                    lang_full(
                                        "verify_challenge_timed",
                                        timeout if timeout > 0 else "",
                                    ),
                                )
                            ),
                            parse_mode='html',
                        )
                    )
                    if not challenge_msg:
                        break # Failed to send message, fallback

                    # In Telethon, we "click" the result.
                    # The listener `image_captcha_listener` will catch the new message from the bot.
                    await results[0].click(self.user.id)

                    # We save the ID of our text message. The listener will handle the bot's message.
                    self.challenge_msg_ids = [challenge_msg.id]
                    self.save_state(
                        {
                            "try_count": self.try_count,
                            "last_active": int(time.time()),
                        }
                    )
                    await exec_api(bot(BlockRequest(id=self.user.id)))
                    self.reset_timer()
                    await super(ImageChallenge, self).start()
                    return

                except asyncio.TimeoutError:
                    console.debug(
                        f"Image captcha bot timeout for {self.user.id}, fallback"
                    )
                    break  # Fallback
                except FloodWaitError as e:
                    console.debug(
                        f"Image captcha triggered flood for {self.user.id}, wait {e.seconds}"
                    )
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    console.error(
                        f"Failed to send image captcha challenge to {self.user.id}: {e}\n{traceback.format_exc()}"
                    )
                    await asyncio.sleep(10)

            console.debug("Failed to get image captcha, fallback to math captcha.")
            fallback_captcha = MathChallenge(self.user, self.can_report)
            await fallback_captcha.start()
            return fallback_captcha

    async def verify(self, success: bool):
        if success:
            await exec_api(bot(UnblockRequest(id=self.user.id)))
            return await self.action(success)
        else:
            self.try_count += 1
            if self.try_count >= setting.get("img_max_retry", 3):
                await self.action(False)
                return True
            console.debug(
                f"User failed to complete image captcha challenge, try count: {self.try_count}"
            )
            self.update_state({"try_count": self.try_count})


class StickerChallenge(CaptchaChallenge):
    def __init__(self, user: User, can_report: bool):
        super().__init__("sticker", user, True, can_report)

    @classmethod
    async def resume(cls, *, user: User, msg: Optional[Message] = None, state: dict):
        captcha = cls(user, state["report"])
        captcha.captcha_start = state["start"]
        captcha.logs = state["logs"]
        captcha.challenge_msg_ids = (
            [state["msg_id"]] if state.get("msg_id") else state.get("msg_ids", [])
        )

        if (timeout := setting.get("timeout", 30)) > 0:
            time_passed = int(time.time()) - int(state["start"])
            if time_passed > timeout:
                # Timeout
                return await captcha.action(False)
            if msg:  # Verify result
                await captcha.verify(msg.sticker)
            else:  # Restore timer
                captcha.reset_timer(timeout - time_passed)
        await super(StickerChallenge, captcha).resume(user=user, msg=msg, state=state)

    async def start(self):
        if self.captcha_write_lock.locked():
            return
        async with self.captcha_write_lock:
            timeout = setting.get("timeout", 30)
            challenge_msg = await exec_api(
                bot.send_message(
                    self.user.id,
                    "\n".join(
                        (
                            lang_full("verify_challenge"),
                            "",
                            code(lang_full("verify_send_sticker")),
                            "",
                            lang_full(
                                "verify_challenge_timed", timeout if timeout > 0 else ""
                            ),
                        )
                    ),
                    parse_mode='html',
                )
            )
            if not challenge_msg:
                return await log(
                    f"Failed to send sticker captcha challenge to {self.user.id}"
                )
            self.challenge_msg_ids = [challenge_msg.id]
            self.save_state()
            self.reset_timer(timeout)
            await super(StickerChallenge, self).start()

    async def verify(self, response: Optional[Document]):
        if self.captcha_write_lock.locked():
            return
        async with self.captcha_write_lock:
            if not response:
                return await the_order.active(self.user.id, "verify_failed")
        await self.action(bool(response))
        return bool(response)


# endregion


@dataclass
class Rule:
    user: User
    msg: Message

    can_report: Optional[bool] = None
    auto_archived: Optional[bool] = None

    def _precondition(self) -> bool:
        # PagerMaid-Telethon uses msg.sender for the sender object
        sender = self.msg.sender
        # A service message in Telethon has a non-None `action` attribute.
        # Also, the sender might be None for some channel actions.
        if not sender:
            return True
        return (
            # Skip for PGM/PMC Developers
            sender.id in (347437156, 583325201, 1148248480, 751686745, 676660002)
            or sender.contact
            or sender.verified
            or (self.msg.chat and self.msg.chat.bot)
            or self.msg.action is not None  # Correct way to check for service messages in Telethon
            or setting.is_verified(sender.id)
        )

    def _get_text(self) -> str:
        return self.msg.text or ""

    async def _get_user_settings(self) -> (bool, bool):
        if isinstance(self.can_report, bool):
            return self.can_report, self.auto_archived
        return await captcha_task.get_user_settings(self.user.id)

    async def _run_rules(self, *, outgoing: bool = False):
        if not outgoing and self._precondition():
            return
        members = inspect.getmembers(self, inspect.iscoroutinefunction)
        members.sort(key=_sort_line_number)
        async with rule_lock:
            for name, func in members:
                docs = func.__doc__ or ""
                try:
                    if not name.startswith("_") and (
                        "outgoing" in docs
                        and outgoing
                        and await func()
                        or "outgoing" not in docs
                        and not self.user.is_self
                        and await func()
                    ):
                        chat_id = self.msg.chat.id if self.msg.chat else self.user.id
                        console.debug(
                            f"Rule triggered: `{name}` (user: {self.user.id} chat: {chat_id})"
                        )
                        break
                except Exception as e:
                    console.error(
                        f"Failed to run rule `{name}`: {e}\n{traceback.format_exc()}"
                    )

    @staticmethod
    def _get_rules_priority() -> tuple:
        prio_list = []
        members = inspect.getmembers(Rule, inspect.iscoroutinefunction)
        members.sort(key=_sort_line_number)
        for name, func in members:
            if name.startswith("_"):
                continue
            docs = func.__doc__ or ""
            if "no_prio" not in docs:
                if result := re.search(r"name:\s?(.+)", docs):
                    name = result[1]
                prio_list.append(name)
        return tuple(prio_list)

    async def initiative(self) -> bool:
        """outgoing"""
        initiative = setting.get("initiative", True)
        initiative and not setting.whitelist.check_id(
            self.msg.chat.id
        ) and setting.whitelist.add_id(self.msg.chat.id)
        return initiative

    async def user_defined(self) -> bool:
        if custom_rule := setting.get("custom_rule"):
            try:
                exec(f"async def _(msg, text, user, me, bot):\n return {custom_rule}")
                return bool(
                    await locals()["_"](
                        self.msg, self._get_text(), self.user, bot.me, bot
                    )
                )
            except Exception as e:
                await log(
                    f"{lang('custom_rule_exec_err')}: {e}\n{traceback.format_exc()}"
                )
        return False

    async def disable_pm(self) -> bool:
        if disabled := setting.get("disable"):
            await the_order.active(self.user.id, "disable_pm_enabled")
            captcha = CaptchaChallenge("none", self.user, False)
            captcha.log_msg(self.msg.text)
            await captcha.send_log("pm_disabled")
        return disabled

    async def chat_history(self) -> bool:
        if (history_count := setting.get("history_count", -1)) > 0:
            count = 0
            # PagerMaid's bot.get_chat_history should internally use iter_messages
            async for msg in bot.get_chat_history(
                self.user.id, limit=history_count + 1
            ):
                if msg.id != self.msg.id:
                    count += 1
            if count >= history_count:
                setting.whitelist.add_id(self.user.id)
                return True
        return False

    async def groups_in_common(self) -> bool:
        if (common_groups := setting.get("groups_in_common")) is not None:
            peer = await bot.get_input_entity(self.user.id)
            if user_full := await exec_api(
                bot(users.GetFullUserRequest(id=peer))
            ):
                if user_full.full_user.common_chats_count >= common_groups:
                    setting.whitelist.add_id(self.user.id)
                    return True
            else:
                console.warn(f"Failed to Get Common Groups for user {self.user.id}")
        return False

    async def premium(self) -> bool:
        sender = self.msg.sender
        if premium := setting.get("premium"):
            captcha = CaptchaChallenge("disable_pm", self.user, False)
            captcha.log_msg(self.msg.text or "")
            if premium == "only" and not sender.premium:
                await the_order.active(self.user.id, "premium_only")
                await captcha.send_log("premium_only")
            elif not sender.premium:
                return False
            elif premium == "ban":
                await the_order.active(self.user.id, "premium_ban")
                await captcha.send_log("premium_ban")
        return premium

    # Whitelist / Blacklist
    async def word_filter(self) -> bool:
        """name: whitelist > blacklist"""
        text = self._get_text()
        if text is None:
            return False
        if array := setting.get("whitelist"):
            for word in array:
                if word not in text:
                    continue
                setting.whitelist.add_id(self.user.id)
                return True
        if array := setting.get("blacklist"):
            for word in array:
                if word not in text:
                    continue
                reason_code = "blacklist_triggered"
                await the_order.active(self.user.id, reason_code)
                # Collect logs
                can_report, _ = await self._get_user_settings()
                captcha = CaptchaChallenge("blacklist", self.user, False, can_report)
                captcha.log_msg(text)
                await captcha.send_log(reason_code)
                return True
        return False

    async def flooding(self) -> bool:
        """name: flood"""
        if the_world_eye.triggered:
            _, auto_archived = await self._get_user_settings()
            not auto_archived and await captcha_task.archive(self.user.id)
            await the_world_eye.add_synchronize(self.user.id)
        return the_world_eye.triggered

    async def add_captcha(self) -> bool:
        """name: captcha"""
        user_id = self.user.id
        if (
            setting.get_challenge_state(user_id)
            and not curr_captcha.get(user_id)
            or not curr_captcha.get(user_id)
        ):
            # Put in challenge queue
            await captcha_task.add(
                user_id, self.msg, *(await self._get_user_settings())
            )
            return True
        return False

    async def verify_challenge_answer(self) -> bool:
        """no_priority"""
        user_id = self.user.id
        if (
            (captcha := curr_captcha.get(user_id))
            and captcha.input
            and captcha.type == "math"
        ):
            text = self._get_text()
            captcha.log_msg(text)
            if await captcha.verify(text):
                await self.msg.delete()
            if curr_captcha.get(user_id) is captcha:
                del curr_captcha[user_id]
            return True
        return False

    async def verify_sticker_response(self) -> bool:
        """no_priority"""
        if (
            (captcha := curr_captcha.get(user_id := self.user.id))
            and captcha.input
            and captcha.type == "sticker"
        ):
            captcha.log_msg(self._get_text())
            if await captcha.verify(self.msg.sticker):
                await self.msg.delete()
            if curr_captcha.get(user_id) is captcha:
                del curr_captcha[user_id]
            return True
        return False


# Watches every image captcha result
@listener(is_plugin=False, incoming=True, outgoing=True, privates_only=True)
async def image_captcha_listener(_, msg: Message):
    # Ignores non-private chat, not via bot, username not equal to image bot
    if (
        not msg.is_private
        or not msg.via_bot
        or msg.via_bot.username != img_captcha_bot
    ):
        return
    user_id = msg.chat.id
    if (
        last_captcha := sqlite.get(f"pmcaptcha.challenge.{user_id}")
    ) and not curr_captcha.get(user_id):
        # Resume last captcha challenge
        if last_captcha["type"] != "img":
            return await log(
                "Failed to resume last captcha challenge: "
                f"Unknown challenge type {last_captcha['type']}"
            )
        sender = await msg.get_sender()
        await ImageChallenge.resume(user=sender, state=last_captcha)
    if not curr_captcha.get(user_id):  # User not in verify state
        return
    captcha, msg_text = curr_captcha[user_id], msg.text or ""
    captcha.reset_timer().update_state({"last_active": int(time.time())})
    if "CAPTCHA_SOLVED" in msg_text:
        await msg.delete()
        await captcha.verify(True)
        del curr_captcha[user_id]
    elif "CAPTCHA_FAILED" in msg_text:
        if "forced" in msg.text:
            await captcha.action(False)
            del curr_captcha[user_id]
            return
        if await captcha.verify(False):
            del curr_captcha[user_id]
            await msg.delete()
    elif "CAPTCHA_FALLBACK" in msg_text:
        await msg.delete()
        # Fallback to selected captcha type
        captcha_type = msg.text.replace("CAPTCHA_FALLBACK", "").strip()
        console.debug(f"Image bot return fallback request, fallback to {captcha_type}")

        # Unstuck
        await exec_api(bot(UnblockRequest(id=user_id)))
        if captcha := curr_captcha.get(user_id):
            captcha.timer_task and captcha.timer_task.cancel()
        setting.get_challenge_state(user_id) and setting.del_challenge_state(user_id)

        if captcha_type == "math":
            new_captcha = MathChallenge(captcha.user, captcha.can_report)
            challenge_msg_id = captcha.challenge_msg_ids[0]
            await new_captcha.start(challenge_msg_id)
            curr_captcha[user_id] = new_captcha
            return


@listener(is_plugin=False, outgoing=True, privates_only=True)
async def initiative_listener(_, msg: Message):
    await Rule(bot.me, msg)._run_rules(outgoing=True)


@listener(
    is_plugin=False,
    incoming=True,
    outgoing=False,
    ignore_edited=True,
    privates_only=True,
    ignore_forwarded=False,
)
async def chat_listener(_, msg: Message):
    sender = await msg.get_sender()
    if sender:
        await Rule(sender, msg)._run_rules()


@listener(
    is_plugin=True,
    outgoing=True,
    command=user_cmd_name,
    parameters=f"<{lang('vocab_cmd')}> [{lang('cmd_param')}]",
    need_admin=True,
    description=f"{lang('plugin_desc')}\n{(lang('check_usage') % code(f',{user_cmd_name} h'))}",
)
async def cmd_entry(_, msg: Message):
    # In PagerMaid-Telethon, the user object is usually msg.sender
    cmd = Command(msg.sender, msg)
    result, err_code, extra = await cmd._run_command()
    if not result:
        if err_code == "NOT_FOUND":
            return await cmd._edit(
                f"{lang('cmd_not_found')}: {code(extra)}\n"
                + lang("check_usage") % code(f",{user_cmd_name} h")
            )
        elif err_code == "INVALID_PARAM":
            return await cmd._edit(lang("invalid_param"))


async def resume_states():
    console.debug("Resuming Captcha States")
    for key, value in sqlite.items():  # type: str, dict
        if key.startswith("pmcaptcha.challenge"):
            user_id = int(key.split(".")[2])
            if user_id not in curr_captcha and (
                challenge := captcha_challenges.get(value.get("type"))
            ):
                # Resume challenge state
                try:
                    user = await bot.get_entity(user_id)
                    await challenge.resume(user=user, state=value)
                except (KeyError, PeerIdInvalidError, ValueError):
                    del sqlite[key]
                    console.debug(f"User {user_id} not found, deleted challenge state")
                except Exception as e:
                    console.error(
                        f"Error occurred when resuming captcha state: {e}\n{traceback.format_exc()}"
                    )
    console.debug("Captcha State Resume Completed")


if __name__ == "plugins.pmcaptcha":
    # Force disabled for old PMCaptcha
    globals().get("SubCommand") and exit(0)
    # Flood Username confirm
    user_want_set_flood_username = None
    # Logger
    console = logs.getChild(cmd_name)
    globals().get("console") is None and exit(0)  # Old version
    # Rule lock
    rule_lock = asyncio.Lock()
    captcha_challenges = {
        "math": MathChallenge,
        "img": ImageChallenge,
        "sticker": StickerChallenge,
    }
    _cancel_task = lambda task: task and task.cancel()  # noqa
    gbl = globals()
    # noinspection PyRedeclaration
    curr_captcha: Dict[
        int, Union[MathChallenge, ImageChallenge, StickerChallenge]
    ] = globals().get("curr_captcha", {})
    if setting := globals().get("setting"):
        del setting
    # noinspection PyRedeclaration
    setting = Setting("pmcaptcha")
    if logging := gbl.get("logging"):
        _cancel_task(logging.task)
        del logging
    # noinspection PyRedeclaration
    logging = Log()
    if the_world_eye := gbl.get("the_world_eye"):
        _cancel_task(the_world_eye.watcher)
        del the_world_eye
    # noinspection PyRedeclaration
    the_world_eye = TheWorldEye()
    if the_order := gbl.get("the_order"):
        _cancel_task(the_order.task)
        del the_order
    # noinspection PyRedeclaration
    the_order = TheOrder()
    if captcha_task := gbl.get("captcha_task"):
        _cancel_task(captcha_task.task)
        del captcha_task
    # noinspection PyRedeclaration
    captcha_task = CaptchaTask()
    if resume_task := gbl.get("resume_task"):
        _cancel_task(resume_task)
    resume_task = asyncio.create_task(resume_states())
    gc.collect()
elif __name__ == "__main__":
    with open("command_list.md", "wb") as f:
        f.write(Command._generate_markdown().encode())
    print("MarkDown Generated.")
