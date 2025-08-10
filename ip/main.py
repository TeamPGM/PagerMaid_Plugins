import httpx
from pagermaid.listener import listener
from pagermaid.enums import Message
from pagermaid.utils import lang


@listener(
    command="ip",
    description="查询 IP 地址信息",
    parameters="<ip>"
)
async def ip_query(message: Message):
    """查询 IP 地址信息"""
    ip = ""
    if message.reply_to_msg_id:
        reply = await message.get_reply_message()
        if reply and reply.text:
            ip = reply.text.strip()
    
    if not ip:
        if hasattr(message, 'parameter') and message.parameter:
            ip = message.parameter[0]

    if not ip:
        return await message.edit("请输入 IP 地址或回复一条消息。")

    url = f"https://api.ip2location.io/?ip={ip}&format=json"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            return await message.edit(f"查询失败: {data['error']['error_message']}")

        result = (
            f"IP: `{data.get('ip')}`\n"
            f"国家: `{data.get('country_name')} ({data.get('country_code')})`\n"
            f"地区: `{data.get('region_name')}`\n"
            f"城市: `{data.get('city_name')}`\n"
            f"经纬度: `{data.get('latitude')}, {data.get('longitude')}`\n"
            f"邮政编码: `{data.get('zip_code')}`\n"
            f"时区: `{data.get('time_zone')}`\n"
            f"ASN: `{data.get('asn')}`\n"
            f"AS: `{data.get('as')}`\n"
            f"是否为代理: `{'是' if data.get('is_proxy') else '否'}`"
        )
        await message.edit(result)
    except httpx.HTTPStatusError as e:
        await message.edit(f"查询失败，HTTP 错误: {e.response.status_code}")
    except Exception as e:
        await message.edit(f"查询失败: {e}")
