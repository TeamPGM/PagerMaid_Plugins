import asyncio
from collections import defaultdict
import os
import zipfile
from PIL import Image
from telethon.tl.functions.messages import GetAllStickersRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.errors import MessageNotModifiedError
from telethon.errors.rpcerrorlist import StickersetInvalidError
from pagermaid import working_dir
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    InputMediaUploadedDocument,
    InputPeerNotifySettings,
    InputStickerSetID,
    InputStickerSetShortName,
    MessageMediaPhoto
)
from pagermaid.listener import listener
from pagermaid.utils import alias_command

lottie_import = True
try:
    from lottie.exporters.gif import export_gif
    from lottie.importers.core import import_tgs
except ImportError:
    lottie_import = False


@listener(is_plugin=True, outgoing=True, command=alias_command("getstickers"),
          description="获取整个贴纸包的贴纸，false 关闭 tgs 转 gif；任意值开启下载所有贴纸包；转 gif 需要手动安装 pypi 依赖 lottie[gif] 。",
          parameters="<任意值>")
async def getstickers(context):
    tgs_gif = True
    if not os.path.isdir('data/sticker/'):
        os.makedirs('data/sticker/')
    if len(context.parameter) == 1 or len(context.parameter) == 2:
        if "false" in context.arguments:
            tgs_gif = False
        if "all" in context.arguments:
            sticker_sets = await context.client(GetAllStickersRequest(0))
            for stickerset in sticker_sets.sets:
                file_ext_ns_ion = "webp"
                wdnmd = InputStickerSetID(id=stickerset.id, access_hash=stickerset.access_hash)
                sticker_set = await context.client(GetStickerSetRequest(wdnmd))
                pack_file = os.path.join('data/sticker/', sticker_set.set.short_name, "pack.txt")
                if os.path.isfile(pack_file):
                    os.remove(pack_file)
                # Sticker emojis
                emojis = defaultdict(str)
                for pack in sticker_set.packs:
                    for document_id in pack.documents:
                        emojis[document_id] += pack.emoticon

                async def download(sticker, emojis, path, file):
                    await context.client.download_media(sticker, file=os.path.join(path, file))
                    with open(pack_file, "a") as f:
                        f.write(f"{{'image_file': '{file}','emojis':{emojis[sticker.id]}}},")
                    if file_ext_ns_ion == 'tgs' and lottie_import and tgs_gif:
                        animated = import_tgs(os.path.join(path, file))
                        export_gif(animated, os.path.join(path, file)[:-3] + 'gif')
                    elif file_ext_ns_ion == 'webp':
                        convert_png(os.path.join(path, file))

                pending_tasks = [
                    asyncio.ensure_future(
                        download(document, emojis, 'data/sticker/' + sticker_set.set.short_name,
                                 f"{i:03d}.{file_ext_ns_ion}")
                    ) for i, document in enumerate(sticker_set.documents)
                ]
                xx = await context.client.send_message(context.chat_id,
                                                       f"正在下载 {sticker_set.set.short_name} "
                                                       f"中的 {sticker_set.set.count} 张贴纸。。。")
                num_tasks = len(pending_tasks)
                while 1:
                    done, pending_tasks = await asyncio.wait(pending_tasks, timeout=2.5,
                                                             return_when=asyncio.FIRST_COMPLETED)
                    if file_ext_ns_ion == 'tgs' and lottie_import and tgs_gif:
                        try:
                            await xx.edit(
                                f"正在下载/转换中，进度： {num_tasks - len(pending_tasks)}/{sticker_set.set.count}")
                        except MessageNotModifiedError:
                            pass
                    if not pending_tasks:
                        break
                await xx.edit("下载完毕，打包上传中。")
                directory_name = sticker_set.set.short_name
                os.chdir("data/sticker/")  # 修改当前工作目录
                zipf = zipfile.ZipFile(directory_name + ".zip", "w", zipfile.ZIP_DEFLATED)
                zipdir(directory_name, zipf)
                zipf.close()
                await context.client.send_file(
                    context.chat_id,
                    directory_name + ".zip",
                    caption=sticker_set.set.short_name,
                    force_document=True,
                    allow_cache=False
                )
                try:
                    os.remove(directory_name + ".zip")
                    os.remove(directory_name)
                except:
                    pass
                os.chdir(working_dir)
                await xx.delete()
                return
    reply_message = await context.get_reply_message()
    if reply_message:
        if not reply_message.sticker:
            await context.edit("请回复一张贴纸。")
            return
    else:
        await context.edit("请回复一张贴纸。")
        return
    sticker = reply_message.sticker
    sticker_attrib = find_instance(sticker.attributes, DocumentAttributeSticker)
    if not sticker_attrib.stickerset:
        await context.edit("回复的贴纸不属于任何贴纸包。")
        return
    is_a_s = is_it_animated_sticker(reply_message)
    file_ext_ns_ion = "webp"
    if is_a_s:
        file_ext_ns_ion = "tgs"
        if tgs_gif and not lottie_import:
            await context.reply('`lottie[gif]` 依赖未安装，tgs 无法转换为 gif ，进行标准格式导出。')
    try:
        sticker_set = await context.client(GetStickerSetRequest(sticker_attrib.stickerset))
    except StickersetInvalidError:
        await context.edit('回复的贴纸不存在于任何贴纸包中。')
        return
    pack_file = os.path.join('data/sticker/', sticker_set.set.short_name, "pack.txt")
    if os.path.isfile(pack_file):
        os.remove(pack_file)
    # Sticker emojis
    emojis = defaultdict(str)
    for pack in sticker_set.packs:
        for document_id in pack.documents:
            emojis[document_id] += pack.emoticon

    async def download(sticker, emojis, path, file):
        await context.client.download_media(sticker, file=os.path.join(path, file))
        with open(pack_file, "a") as f:
            f.write(f"{{'image_file': '{file}','emojis':{emojis[sticker.id]}}},")
        if file_ext_ns_ion == 'tgs' and lottie_import and tgs_gif:
            animated = import_tgs(os.path.join(path, file))
            export_gif(animated, os.path.join(path, file)[:-3] + 'gif')
        elif file_ext_ns_ion == 'webp':
            convert_png(os.path.join(path, file))

    pending_tasks = [
        asyncio.ensure_future(
            download(document, emojis, 'data/sticker/' + sticker_set.set.short_name,
                     f"{i:03d}.{file_ext_ns_ion}")
        ) for i, document in enumerate(sticker_set.documents)
    ]
    await context.edit(
        f"正在下载 {sticker_set.set.short_name} 中的 {sticker_set.set.count} 张贴纸。。。")
    num_tasks = len(pending_tasks)
    while 1:
        done, pending_tasks = await asyncio.wait(pending_tasks, timeout=2.5,
                                                 return_when=asyncio.FIRST_COMPLETED)
        if file_ext_ns_ion == 'tgs' and lottie_import and tgs_gif:
            try:
                await context.edit(
                    f"正在下载/转换中，进度： {num_tasks - len(pending_tasks)}/{sticker_set.set.count}")
            except MessageNotModifiedError:
                pass
        if not pending_tasks:
            break
    await context.edit("下载完毕，打包上传中。")
    directory_name = sticker_set.set.short_name
    os.chdir("data/sticker/")  # 修改当前工作目录
    zipf = zipfile.ZipFile(directory_name + ".zip", "w", zipfile.ZIP_DEFLATED)
    zipdir(directory_name, zipf)
    zipf.close()
    await context.client.send_file(
        context.chat_id,
        directory_name + ".zip",
        caption=sticker_set.set.short_name,
        force_document=True,
        allow_cache=False,
        reply_to=reply_message.id
    )
    try:
        os.remove(directory_name + ".zip")
        os.remove(directory_name)
    except:
        pass
    os.chdir(working_dir)
    await context.delete()


def find_instance(items, class_or_tuple):
    for item in items:
        if isinstance(item, class_or_tuple):
            return item
    return None


def is_it_animated_sticker(message):
    try:
        if message.media and message.media.document:
            mime_type = message.media.document.mime_type
            if "tgsticker" in mime_type:
                return True
            else:
                return False
        else:
            return False
    except:
        return False


def zipdir(path, ziph):
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))
            os.remove(os.path.join(root, file))


def convert_png(path):
    im = Image.open(path)
    im = im.convert('RGBA')
    new_path = path.replace(".webp", ".png")
    im.save(new_path, 'PNG')
    return new_path
