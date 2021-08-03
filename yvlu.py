from os.path import exists
from os import makedirs, remove
from PIL import Image, ImageFont, ImageDraw
from requests import get
from telethon.tl.functions.users import GetFullUserRequest
from pagermaid.listener import listener
from pagermaid.utils import alias_command


def font(path, size):
    return ImageFont.truetype(f'{path}ZhuZiAWan-2.ttc', size=size, encoding="utf-8")


def cut(obj, sec):
    return [obj[i:i + sec] for i in range(0, len(obj), sec)]


def yv_lu_process_image(name, text, photo, path):
    if len(name) > 27:
        name = name[:27] + '...'
    text = cut(text, 22)
    # 用户不存在头像时
    if not photo:
        photo = Image.open(f'{path}4.png')
        # 对图片写字
        draw = ImageDraw.Draw(photo)
        # 计算使用该字体占据的空间
        # 返回一个 tuple (width, height)
        # 分别代表这行字占据的宽和高
        text_width = font(path, 60).getsize(name[0])
        if name[0].isalpha():
            text_coordinate = int((photo.size[0] - text_width[0]) / 2), int((photo.size[1] - text_width[1]) / 2) - 10
        else:
            text_coordinate = int((photo.size[0] - text_width[0]) / 2), int((photo.size[1] - text_width[1]) / 2)
        draw.text(text_coordinate, name[0], (255, 110, 164), font(path, 60))
    else:
        photo = Image.open(f'{path}{photo}')
    # 读取图片
    img1, img2, img3, mask = Image.open(f'{path}1.png'), Image.open(f'{path}2.png'), \
                             Image.open(f'{path}3.png'), Image.open(f'{path}mask.png')
    size1, size2, size3 = img1.size, img2.size, img3.size
    photo_size = photo.size
    mask_size = mask.size
    scale = photo_size[1] / mask_size[1]
    photo = photo.resize((int(photo_size[0] / scale), int(photo_size[1] / scale)), Image.LANCZOS)
    mask1 = Image.new('RGBA', mask_size)
    mask1.paste(photo, mask=mask)
    # 创建空图片
    result = Image.new(img1.mode, (size1[0], size1[1] + size2[1] * len(text) + size3[1]))

    # 读取粘贴位置
    loc1, loc3, loc4 = (0, 0), (0, size1[1] + size2[1] * len(text)), (6, size1[1] + size2[1] * len(text) - 23)

    # 对图片写字
    draw = ImageDraw.Draw(img1)
    draw.text((60, 10), name, (255, 110, 164), font(path, 18))
    for i in range(len(text)):
        temp = Image.open(f'{path}2.png')
        draw = ImageDraw.Draw(temp)
        draw.text((60, 0), text[i], (255, 255, 255), font(path, 18))
        result.paste(temp, (0, size1[1] + size2[1] * i))

    # 粘贴图片
    result.paste(img1, loc1)
    result.paste(img3, loc3)
    result.paste(mask1, loc4)

    # 保存图片
    result.save(f'{path}result.png')


@listener(is_plugin=True, outgoing=True, command=alias_command("yvlu"),
          description="将回复的消息转换成语录")
async def yv_lu(context):
    if not context.reply_to_msg_id:
        await context.edit('你需要回复一条消息。')
        return
    if not exists('plugins/yvlu/'):
        makedirs('plugins/yvlu/')
    await context.edit('处理中。。。')
    for num in range(1, 5):
        if not exists('plugins/yvlu/' + str(num) + '.png'):
            re = get('https://raw.githubusercontent.com/Xtao-Labs/PagerMaid_Plugins/master/yvlu/' + str(num) + '.png')
            with open('plugins/yvlu/' + str(num) + '.png', 'wb') as bg:
                bg.write(re.content)
    if not exists('plugins/yvlu/mask.png'):
        re = get('https://raw.githubusercontent.com/Xtao-Labs/PagerMaid_Plugins/master/yvlu/mask.png')
        with open('plugins/yvlu/mask.png', 'wb') as bg:
            bg.write(re.content)
    if not exists('plugins/yvlu/ZhuZiAWan-2.ttc'):
        await context.edit('下载字体中。。。')
        re = get('https://raw.githubusercontent.com/Xtao-Labs/Telegram_PaimonBot/master/assets/fonts/ZhuZiAWan-2.ttc')
        with open('plugins/yvlu/ZhuZiAWan-2.ttc', 'wb') as bg:
            bg.write(re.content)
    reply_message = await context.get_reply_message()
    user_id = reply_message.sender_id
    target_user = await context.client(GetFullUserRequest(user_id))
    await context.client.download_profile_photo(
        target_user.user.id,
        "plugins/yvlu/" + str(target_user.user.id) + ".jpg",
        download_big=True
    )
    name = target_user.user.first_name
    if target_user.user.last_name:
        name += f' {target_user.user.last_name}'
    if exists("plugins/yvlu/" + str(target_user.user.id) + ".jpg"):
        yv_lu_process_image(name, reply_message.text, f"{target_user.user.id}.jpg", 'plugins/yvlu/')
        remove("plugins/yvlu/" + str(target_user.user.id) + ".jpg")
    else:
        yv_lu_process_image(name, reply_message.text, None, 'plugins/yvlu/')
    force_document = True
    if context.arguments:
        force_document = False
    await context.client.send_file(
        context.chat_id,
        'plugins/yvlu/result.png',
        force_document=force_document,
        reply_to=context.message.reply_to_msg_id
    )
    await context.delete()
