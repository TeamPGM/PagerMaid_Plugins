""" QR Code utilities (Pillow + pyqrcode + pyzbar) """

import os
import importlib
from io import BytesIO

from PIL import Image
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils import pip_install


# Dependencies
dependencies = {
    "qrcode": "qrcode[pil]",
    "pyzbar": "pyzbar",
}

for module, package in dependencies.items():
    try:
        importlib.import_module(module)
    except ModuleNotFoundError:
        pip_install(package)

def is_alpine_linux():
    return os.path.exists("/etc/alpine-release")

if is_alpine_linux():
    from pyzbar import zbar_library
    import ctypes
    
    def force_load():
        return ctypes.CDLL('libzbar.so.0'), []

    zbar_library.load = force_load


genqr_help = (
    "**生成二维码**\n\n"
    "- **命令:** `genqr <文本内容>`\n"
    "- **功能:** 根据提供的文本内容生成一张二维码图片。"
)


@listener(command="genqr", description="生成二维码。\n\n" + genqr_help, parameters="<文本内容>")
async def gen_qr(message: Message):
    text = message.arguments

    if not text:
        await message.reply("请提供要编码的文本。")
        return

    try:
        import qrcode
    except ImportError:
        await message.reply("缺少依赖：请先安装 `qrcode` 模块。")
        return

    img = qrcode.make(text)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.name = "qr.png"
    buffer.seek(0)

    await message.client.send_file(message.chat_id, buffer, caption="二维码生成完成")
    buffer.close()


parseqr_help = (
    "**解析二维码**\n\n"
    "- **命令:** `parseqr`\n"
    "- **功能:** 解析图片中的二维码。可以通过回复一张包含二维码的图片，或者发送图片时在配文中加上此命令来使用。"
)


@listener(command="parseqr", description="解析二维码。\n\n" + parseqr_help)
async def parse_qr(message: Message):
    reply = await message.get_reply_message()
    target = reply or message

    if not target or not target.media:
        await message.reply("请提供要解析的二维码图片（可以用回复方式）。")
        return

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        await message.reply("缺少依赖：请先安装 `pyzbar` 并确保系统已安装 zbar 库。")
        return

    img_bytes = await target.download_media(bytes)
    if not img_bytes:
        await message.reply("图片下载失败。")
        return

    img = Image.open(BytesIO(img_bytes))
    decoded = pyzbar_decode(img)

    if not decoded:
        await message.reply("未检测到二维码。")
    else:
        result_text = "\n".join([d.data.decode("utf-8", errors="ignore") for d in decoded])
        await message.reply(f"二维码内容：\n{result_text}")
