import re
import asyncio
from io import BytesIO

from PIL import Image
from telethon import functions, utils
from telethon.tl import types
from telethon.errors.rpcerrorlist import StickersetInvalidError

from pagermaid.listener import listener
from pagermaid.services import sqlite

# --- Constants ---
DB_STICKER_PACK_NAME = 'custom.strx.sticker_pack_name'

# --- Pillow Resampling Compatibility ---
try:
    from PIL.Image import Resampling
    BICUBIC = Resampling.BICUBIC
except ImportError:
    BICUBIC = Image.BICUBIC


def normalize_sticker_image_sync(input_bytes: BytesIO) -> BytesIO:
    input_bytes.seek(0)
    im = Image.open(input_bytes).convert("RGBA")
    max_side = 512
    w, h = im.size
    if (w == max_side and h <= max_side) or (h == max_side and w <= max_side):
        resized = im
    else:
        scale = max_side / max(w, h)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        resized = im.resize((new_w, new_h), BICUBIC)
    out = BytesIO()
    resized.save(out, format="WEBP", lossless=True, quality=100, method=5)
    out.seek(0)
    return out

async def normalize_sticker_image_async(input_bytes: BytesIO) -> BytesIO:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, normalize_sticker_image_sync, input_bytes
    )


async def _add_sticker_to_set(client, context, sticker_file: BytesIO, mime_type: str, pack_name: str, emoji: str):
    """
    Internal function to upload a prepared sticker file and add it to a set.
    """
    # 1. Upload the prepared file to Telegram
    try:
        sticker_file.name = "sticker.webp" if "webp" in mime_type else "sticker.tgs"
        media_file = await client.upload_file(sticker_file)
        result = await client(functions.messages.UploadMediaRequest(
            peer=types.InputPeerSelf(),
            media=types.InputMediaUploadedDocument(
                file=media_file,
                mime_type=mime_type,
                attributes=[],
            )
        ))
        if not (isinstance(result, types.MessageMediaDocument) and getattr(result, "document", None)):
            raise TypeError("上传结果不是有效的 Document")
        uploaded_document = result.document
    except Exception as e:
        await context.edit(f"❌ 添加到贴纸包失败：上传出错: {e}")
        return

    # 2. Convert to InputDocument
    input_doc = utils.get_input_document(uploaded_document)
    sticker_item = types.InputStickerSetItem(document=input_doc, emoji=emoji)
    sticker_pack_link = f"t.me/addstickers/{pack_name}"

    # 3. Try to add to an existing pack
    try:
        await client(functions.stickers.AddStickerToSetRequest(
            stickerset=types.InputStickerSetShortName(short_name=pack_name),
            sticker=sticker_item
        ))
        await context.edit(f"✅ 已成功添加贴纸 `{emoji}`", link_preview=False)
        return
    except StickersetInvalidError:
        pass  # Pack doesn't exist, proceed to creation
    except Exception as e:
        if "STICKERSET_INVALID" not in str(e):
            await context.edit(f"❌ 添加到贴纸包失败：{e}")
            return

    # 4. Create a new pack if it doesn't exist
    try:
        await client(functions.stickers.CreateStickerSetRequest(
            user_id=types.InputUserSelf(),
            title=pack_name,
            short_name=pack_name,
            stickers=[sticker_item],
        ))
        await context.edit(f"🎉 已创建新的贴纸包并添加 `{emoji}`：[{pack_name}]({sticker_pack_link})", link_preview=False)
    except Exception as e:
        if "SHORT_NAME_OCCUPIED" in str(e) or "already exists" in str(e):
            try:
                await client(functions.stickers.AddStickerToSetRequest(
                    stickerset=types.InputStickerSetShortName(short_name=pack_name),
                    sticker=sticker_item
                ))
                await context.edit(f"✅ 已成功添加贴纸 `{emoji}`", link_preview=False)
            except Exception as e2:
                await context.edit(f"❌ 添加到贴纸包失败：尝试加入已存在的包失败: {e2}")
        else:
            await context.edit(f"❌ 添加到贴纸包失败：创建包失败: {e}")


@listener(command="strx",
          description="回复贴纸或图片添加到自己的贴纸包。",
          parameters="[<pack_name> | <emoji>]")
async def sticker_add(context):
    """Main handler for the sticker add plugin."""
    args = context.arguments
    reply = await context.get_reply_message()

    if args and not reply:
        pack_name = args
        if not re.match("^[a-zA-Z][a-zA-Z0-9_]*$", pack_name):
            await context.edit('🚫 错误：贴纸包名称必须以字母开头，且只包含字母、数字和下划线。')
            return
        if len(pack_name) > 64:
            await context.edit('🚫 错误：贴纸包名称不能超过64个字符。')
            return
        sqlite[DB_STICKER_PACK_NAME] = pack_name
        await context.edit(f"✅ 贴纸包名称已设置为: `{pack_name}`")
        return

    if reply and (reply.sticker or reply.photo or (reply.document and 'image' in reply.document.mime_type)):
        pack_name = sqlite.get(DB_STICKER_PACK_NAME)
        if not pack_name:
            await context.edit("⚠️ 您尚未设置贴纸包名称，请使用 `-strx <pack_name>` 进行设置。")
            return

        await context.edit("⏳ 正在处理中，请稍候...")
        
        custom_emoji = args if args else None
        sticker_native_emoji = None
        default_emoji = '\U0001F5BC'

        if reply.sticker:
            sticker_native_emoji = next((attr.alt for attr in reply.sticker.attributes if isinstance(attr, types.DocumentAttributeSticker)), None)
        
        emoji = custom_emoji or sticker_native_emoji or default_emoji

        sticker_file = None
        mime_type = None

        if reply.sticker:
            mime_type = reply.sticker.mime_type
            if mime_type == 'application/x-tgsticker':
                sticker_file = await reply.download_media(file=BytesIO())
                sticker_file.seek(0)
            elif mime_type == 'image/webp':
                raw_file = await reply.download_media(file=BytesIO())
                try:
                    sticker_file = await normalize_sticker_image_async(raw_file)
                except Exception as e:
                    await context.edit(f"❌ 添加到贴纸包失败：图片处理失败: {e}")
                    return
            else:
                await context.edit(f"🤷 暂不支持此贴纸类型 ({mime_type})，例如视频贴纸。")
                return

        elif reply.photo or (reply.document and 'image' in reply.document.mime_type): # 图片
            mime_type = 'image/webp'
            raw_file = await reply.download_media(file=BytesIO())
            try:
                sticker_file = await normalize_sticker_image_async(raw_file)
            except Exception as e:
                await context.edit(f"❌ 添加到贴纸包失败：图片处理失败: {e}")
                return
                
        if not sticker_file:
            await context.edit('❓ 未能成功处理回复的消息。')
            return

        await _add_sticker_to_set(
            client=context.client,
            context=context,
            sticker_file=sticker_file,
            mime_type=mime_type,
            pack_name=pack_name,
            emoji=emoji
        )
        return

    pack_name = sqlite.get(DB_STICKER_PACK_NAME)
    if pack_name:
        await context.edit(
            f"""ℹ️ 当前贴纸包为: `{pack_name}`
        🔗 [点此查看](t.me/addstickers/{pack_name})
        
        👉 **用法:**
         • 回复图片/贴纸并发送 `-strx`
         • 回复图片/贴纸并发送 `-strx 😎` 来自定义emoji""",
            link_preview=False
        )
    else:
        await context.edit("👉 请先设置贴纸包名称：`-strx <pack_name>`")
    return