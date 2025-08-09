import asyncio
import json
import pathlib
import traceback

import httpx
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import bot


@listener(
    command="speedtest",
    description="使用 speedtest-cli 测试当前服务器的网络速度。",
)
async def speedtest(message: Message):
    """使用 speedtest-cli 测试当前服务器的网络速度。"""
    script_dir = pathlib.Path("data/speedtest")
    script_path = script_dir / "speedtest.py"

    if not script_path.is_file():
        await message.edit("正在下载 speedtest-cli...")
        try:
            script_dir.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(
                    "https://raw.githubusercontent.com/PeterLinuxOSS/speedtest-cli/c0d4fb7c45fc59fdfd14fa6d88fe791bca110b9f/speedtest.py"
                )
                r.raise_for_status()
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(r.text)
        except Exception:
            await message.edit(f"下载 speedtest-cli 失败：\n<code>{traceback.format_exc()}</code>")
            return

    await message.edit("正在进行速度测试...")
    process = await asyncio.create_subprocess_exec(
        "python3",
        str(script_path),
        "--share",
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()

    if process.returncode != 0:
        await message.edit("执行 speedtest-cli 失败。")
        return

    try:
        result = json.loads(stdout.decode())
        share_url = result.get("share")
        if not share_url:
            await message.edit("未能获取到分享链接。")
        else:
            await bot.send_file(message.chat_id, share_url)
            await message.delete()
    except (json.JSONDecodeError, KeyError):
        await message.edit(f"解析结果失败：\n<code>{traceback.format_exc()}</code>")
