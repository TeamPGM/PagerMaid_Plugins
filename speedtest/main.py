import json
import pathlib
import re
import traceback

import httpx
from sys import executable
from typing import TYPE_CHECKING
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import bot
from pagermaid.utils import execute

if TYPE_CHECKING:
    from pagermaid.enums.command import CommandHandler

script_dir = pathlib.Path("data/speedtest")
script_dir.mkdir(parents=True, exist_ok=True)
script_path = script_dir / "speedtest.py"


async def update_speedtest_script(force: bool = False):
    """更新 speedtest-cli 脚本到最新版本。"""
    if not script_path.is_file() or force:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                "https://raw.githubusercontent.com/PeterLinuxOSS/speedtest-cli/master/speedtest.py"
            )
            r.raise_for_status()
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(r.text)


@listener(
    command="speedtest",
    description="使用 speedtest-cli 测试当前服务器的网络速度。",
)
async def speedtest(message: Message):
    """使用 speedtest-cli 测试当前服务器的网络速度。"""
    if not script_path.is_file():
        await message.edit("正在下载 speedtest-cli...")
        try:
            await update_speedtest_script()
        except Exception:
            await message.edit(f"下载 speedtest-cli 失败：\n<code>{traceback.format_exc()}</code>", parse_mode="html")
            return

    await message.edit("正在进行速度测试...")
    process = None
    try:
        process = await execute(" ".join([str(executable), str(script_path), "--share", "--json"]))
        json_match = re.search(r'^\{.*\}', process, re.DOTALL)
        if not json_match:
            raise ValueError("未能匹配到 JSON 格式的结果。")
        result = json.loads(json_match.group(0))
        share_url = result.get("share")
        if not share_url:
            await message.edit("未能获取到分享链接。")
        else:
            await bot.send_file(message.chat_id, share_url)
            await message.safe_delete()
    except (json.JSONDecodeError, KeyError):
        if process:
            await message.edit(f"解析结果失败：{process}")
            return
        await message.edit(f"解析结果失败：\n<code>{traceback.format_exc()}</code>", parse_mode="html")


speedtest: "CommandHandler"


@speedtest.sub_command(command="update")
async def speedtest_update(message: Message):
    """强制更新 speedtest-cli 脚本到最新版本。"""
    try:
        await update_speedtest_script(force=True)
        await message.edit("speedtest-cli 脚本已更新到最新版本。")
    except Exception:
        await message.edit(f"更新 speedtest-cli 失败：\n<code>{traceback.format_exc()}</code>", parse_mode="html")
