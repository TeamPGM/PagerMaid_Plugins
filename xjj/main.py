import asyncio

from pagermaid.listener import listener
from pagermaid.enums import Message, AsyncClient


async def get_video_url(client: AsyncClient, retries: int = 3, delay: float = 1.5) -> str:
    for attempt in range(retries):
        try:
            res = await client.get("https://api.yujn.cn/api/zzxjj.php?type=video", timeout=10.0, follow_redirects=True)
            return str(res.url)
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                raise e


@listener(command="xjj", description="小姐姐视频")
async def xjj(message: Message, client: AsyncClient):
    if message.chat and message.chat.id == -1001441461877:
        # 用户群禁止使用此功能
        await message.edit("本群禁止使用此功能。")
        return
    await message.edit("小姐姐视频生成中 . . .")
    try:
        url = await get_video_url(client)
        try:
            await message.edit("写真我拍好辣，上传中 . . .")
            await message.client.send_file(message.chat_id, url, caption="小姐姐来辣~⁄(⁄ ⁄•⁄ω⁄•⁄ ⁄)⁄)")
            await message.safe_delete()
        except Exception as e:
            await message.edit(f"出错了呜呜呜 ~ {e.__class__.__name__}")
    except Exception as e:
        await message.edit(f"出错了呜呜呜 ~ {e.__class__.__name__}")
