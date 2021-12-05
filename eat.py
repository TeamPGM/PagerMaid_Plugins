""" PagerMaid module to handle sticker collection. """

from PIL import Image
from os.path import exists
from os import remove
from requests import get
from random import randint

from telethon.events import NewMessage
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.patched import Message
from telethon.tl.types import Channel, MessageEntityMentionName, MessageEntityPhone, MessageEntityBotCommand
from telethon.errors.rpcerrorlist import ChatSendStickersForbiddenError
from struct import error as StructError
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid import redis, config, bot, user_id
from collections import defaultdict
import json

try:
    git_source = config['git_source']
except:
    git_source = "https://raw.githubusercontent.com/Xtao-Labs/PagerMaid_Plugins/master/"
positions = {
    "1": [297, 288],
    "2": [85, 368],
    "3": [127, 105],
    "4": [76, 325],
    "5": [256, 160],
    "6": [298, 22],
}
notifyStrArr = {
    "6": "踢人",
}
extensionConfig = {}
max_number = len(positions)
configFilePath = 'plugins/eat/config.json'
configFileRemoteUrlKey = "eat.configFileRemoteUrl"


async def get_full_id(object_n):
    if isinstance(object_n, Channel):
        return (await bot(GetFullChannelRequest(object_n.id))).full_chat.id  # noqa
    elif not object_n:
        return user_id
    return (await bot(GetFullUserRequest(object_n.id))).user.id


async def eat_it(context, uid, base, mask, photo, number, layer=0):
    mask_size = mask.size
    photo_size = photo.size
    if mask_size[0] < photo_size[0] and mask_size[1] < photo_size[1]:
        scale = photo_size[1] / mask_size[1]
        photo = photo.resize((int(photo_size[0] / scale), int(photo_size[1] / scale)), Image.LANCZOS)
    photo = photo.crop((0, 0, mask_size[0], mask_size[1]))
    mask1 = Image.new('RGBA', mask_size)
    mask1.paste(photo, mask=mask)
    numberPosition = positions[str(number)]
    isSwap = False
    # 处理头像，放到和背景同样大小画布的特定位置
    try:
        isSwap = extensionConfig[str(number)]["isSwap"]
    except:
        pass
    if isSwap:
        photoBg = Image.new('RGBA', base.size)
        photoBg.paste(mask1, (numberPosition[0], numberPosition[1]), mask1)
        photoBg.paste(base, (0, 0), base)
        base = photoBg
    else:
        base.paste(mask1, (numberPosition[0], numberPosition[1]), mask1)

    # 增加判断是否有第二个头像孔
    isContinue = len(numberPosition) > 2 and layer == 0
    if isContinue:
        await context.client.download_profile_photo(
            uid,
            "plugins/eat/" + str(uid) + ".jpg",
            download_big=True
        )
        try:
            markImg = Image.open("plugins/eat/" + str(uid) + ".jpg")
            maskImg = Image.open("plugins/eat/mask" + str(numberPosition[2]) + ".png")
        except:
            await context.edit(f"图片模版加载出错，请检查并更新配置：mask{str(numberPosition[2])}.png")
            return base
        base = await eat_it(context, uid, base, maskImg, markImg, numberPosition[2], layer + 1)

    temp = base.size[0] if base.size[0] > base.size[1] else base.size[1]
    if temp != 512:
        scale = 512 / temp
        base = base.resize((int(base.size[0] * scale), int(base.size[1] * scale)), Image.LANCZOS)

    return base


async def updateConfig(context):
    configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
    if configFileRemoteUrl:
        if downloadFileFromUrl(configFileRemoteUrl, configFilePath) != 0:
            redis.set(configFileRemoteUrlKey, configFileRemoteUrl)
            return -1
        else:
            return await loadConfigFile(context, True)
    return 0


def downloadFileFromUrl(url, filepath):
    try:
        re = get(url)
        with open(filepath, 'wb') as ms:
            ms.write(re.content)
    except:
        return -1
    return 0


async def loadConfigFile(context, forceDownload=False):
    global positions, notifyStrArr, extensionConfig
    try:
        with open(configFilePath, 'r', encoding='utf8') as cf:
            # 读取已下载的配置文件
            remoteConfigJson = json.load(cf)
            # positionsStr = json.dumps(positions)
            # positions = json.loads(positionsStr)

            # 读取配置文件中的positions
            positionsStr = json.dumps(remoteConfigJson["positions"])
            data = json.loads(positionsStr)
            # 与预设positions合并
            positions = mergeDict(positions, data)

            # 读取配置文件中的notifies
            data = json.loads(json.dumps(remoteConfigJson["notifies"]))
            # 与预设positions合并
            notifyStrArr = mergeDict(notifyStrArr, data)

            # 读取配置文件中的extensionConfig
            try:
                data = json.loads(json.dumps(remoteConfigJson["extensionConfig"]))
                # 与预设extensionConfig合并
                extensionConfig = mergeDict(extensionConfig, data)
            except:
                # 新增扩展配置，为了兼容旧的配置文件更新不出错，无视异常
                pass

            # 读取配置文件中的needDownloadFileList
            data = json.loads(json.dumps(remoteConfigJson["needDownloadFileList"]))
            # 下载列表中的文件
            for fileurl in data:
                try:
                    fsplit = fileurl.split("/")
                    filePath = f"plugins/eat/{fsplit[len(fsplit) - 1]}"
                    if not exists(filePath) or forceDownload:
                        downloadFileFromUrl(fileurl, filePath)

                except:
                    await context.edit(f"下载文件异常，url：{fileurl}")
                    return -1
    except:
        return -1
    return 0


def mergeDict(d1, d2):
    dd = defaultdict(list)

    for d in (d1, d2):
        for key, value in d.items():
            dd[key] = value
    return dict(dd)


async def downloadFileByIds(ids, context):
    idsStr = f',{",".join(ids)},'
    try:
        with open(configFilePath, 'r', encoding='utf8') as cf:
            # 读取已下载的配置文件
            remoteConfigJson = json.load(cf)
            data = json.loads(json.dumps(remoteConfigJson["needDownloadFileList"]))
            # 下载列表中的文件
            sucSet = set()
            failSet = set()
            for fileurl in data:
                try:
                    fsplit = fileurl.split("/")
                    fileFullName = fsplit[len(fsplit) - 1]
                    fileName = fileFullName.split(".")[0].replace("eat", "").replace("mask", "")
                    if f',{fileName},' in idsStr:
                        filePath = f"plugins/eat/{fileFullName}"
                        if downloadFileFromUrl(fileurl, filePath) == 0:
                            sucSet.add(fileName)
                        else:
                            failSet.add(fileName)
                except:
                    failSet.add(fileName)
                    await context.edit(f"下载文件异常，url：{fileurl}")
            notifyStr = "更新模版完成"
            if len(sucSet) > 0:
                notifyStr = f'{notifyStr}\n成功模版如下：{"，".join(sucSet)}'
            if len(failSet) > 0:
                notifyStr = f'{notifyStr}\n失败模版如下：{"，".join(failSet)}'
            await context.edit(notifyStr)
    except:
        await context.edit("更新下载模版图片失败，请确认配置文件是否正确")


@listener(is_plugin=True, outgoing=True, command=alias_command("eat"),
          description="生成一张 吃头像 图片\n"
                      "可选：当第二个参数是数字时，读取预存的配置；\n\n"
                      "当第二个参数是.开头时，头像旋转180°，并且判断r后面是数字则读取对应的配置生成\n\n"
                      "当第二个参数是/开头时，在/后面加url则从url下载配置文件保存到本地，如果就一个/，则直接更新配置文件，删除则是/delete；或者/后面加模版id可以手动更新指定模版配置\n\n"
                      "当第二个参数是-开头时，在-后面加上模版id，即可设置默认模版-eat直接使用该模版，删除默认模版是-eat -\n\n"
                      "当第二个参数是!或者！开头时，列出当前可用模版",
          parameters="<username/uid> [随意内容]")
async def eat(context: NewMessage.Event):
    assert isinstance(context.message, Message)
    if len(context.parameter) > 2:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    diu_round = False
    from_user = user_object = context.sender
    from_user_id = await get_full_id(from_user)
    if context.reply_to_msg_id:
        reply_message = await context.get_reply_message()
        try:
            user_id = reply_message.sender_id
        except AttributeError:
            await context.edit("出错了呜呜呜 ~ 无效的参数。")
            return
        if user_id > 0:
            target_user = await context.client(GetFullUserRequest(user_id))
            target_user_id = target_user.user.id
        else:
            target_user = await context.client(GetFullChannelRequest(user_id))
            target_user_id = target_user.full_chat.id
    else:
        user_raw = ""
        if len(context.parameter) == 1 or len(context.parameter) == 2:
            user_raw = user = context.parameter[0]
            if user.isnumeric():
                user = int(user)
        else:
            user = from_user_id
        if context.message.entities is not None:
            if isinstance(context.message.entities[0], MessageEntityMentionName):
                target_user = await context.client(GetFullUserRequest(context.message.entities[0].user_id))
                target_user_id = target_user.user.id
            elif isinstance(context.message.entities[0], MessageEntityPhone):
                if user > 0:
                    target_user = await context.client(GetFullUserRequest(user))
                    target_user_id = target_user.user.id
                else:
                    target_user = await context.client(GetFullChannelRequest(user))
                    target_user_id = target_user.full_chat.id
            elif isinstance(context.message.entities[0], MessageEntityBotCommand):
                target_user = await context.client(GetFullUserRequest(user_object.id))
                target_user_id = target_user.user.id
            else:
                return await context.edit("出错了呜呜呜 ~ 参数错误。")
        elif user_raw[:1] in [".", "/", "-", "!"]:
            target_user_id = await get_full_id(from_user)
        else:
            try:
                user_object = await context.client.get_entity(user)
                target_user_id = await get_full_id(user_object)
            except (TypeError, ValueError, OverflowError, StructError) as exception:
                if str(exception).startswith("Cannot find any entity corresponding to"):
                    await context.edit("出错了呜呜呜 ~ 指定的用户不存在。")
                    return
                if str(exception).startswith("No user has"):
                    await context.edit("出错了呜呜呜 ~ 指定的道纹不存在。")
                    return
                if str(exception).startswith("Could not find the input entity for") or isinstance(exception,
                                                                                                  StructError):
                    await context.edit("出错了呜呜呜 ~ 无法通过此 UserID 找到对应的用户。")
                    return
                if isinstance(exception, OverflowError):
                    await context.edit("出错了呜呜呜 ~ 指定的 UserID 已超出长度限制，您确定输对了？")
                    return
                raise exception
    photo = await context.client.download_profile_photo(
        target_user_id,
        "plugins/eat/" + str(target_user_id) + ".jpg",
        download_big=True
    )

    reply_to = context.message.reply_to_msg_id
    if exists("plugins/eat/" + str(target_user_id) + ".jpg"):
        for num in range(1, max_number + 1):
            print(num)
            if not exists('plugins/eat/eat' + str(num) + '.png'):
                re = get(f'{git_source}eat/eat' + str(num) + '.png')
                with open('plugins/eat/eat' + str(num) + '.png', 'wb') as bg:
                    bg.write(re.content)
            if not exists('plugins/eat/mask' + str(num) + '.png'):
                re = get(f'{git_source}eat/mask' + str(num) + '.png')
                with open('plugins/eat/mask' + str(num) + '.png', 'wb') as ms:
                    ms.write(re.content)
        number = randint(1, max_number)
        try:
            p1 = 0
            p2 = 0
            if len(context.parameter) == 1:
                p1 = context.parameter[0]
                if p1[0] == ".":
                    diu_round = True
                    if len(p1) > 1:
                        try:
                            p2 = int("".join(p1[1:]))
                        except:
                            # 可能也有字母的参数
                            p2 = "".join(p1[1:])
                elif p1[0] == "-":
                    if len(p1) > 1:
                        try:
                            p2 = int("".join(p1[1:]))
                        except:
                            # 可能也有字母的参数
                            p2 = "".join(p1[1:])
                    if p2:
                        redis.set("eat.default-config", p2)
                        await context.edit(f"已经设置默认配置为：{p2}")
                    else:
                        redis.delete("eat.default-config")
                        await context.edit(f"已经清空默认配置")
                    return
                elif p1[0] == "/":
                    await context.edit(f"正在更新远程配置文件")
                    if len(p1) > 1:
                        # 获取参数中的url
                        p2 = "".join(p1[1:])
                        if p2 == "delete":
                            redis.delete(configFileRemoteUrlKey)
                            await context.edit(f"已清空远程配置文件url")
                            return
                        if p2.startswith("http"):
                            # 下载文件
                            if downloadFileFromUrl(p2, configFilePath) != 0:
                                await context.edit(f"下载配置文件异常，请确认url是否正确")
                                return
                            else:
                                # 下载成功，加载配置文件
                                redis.set(configFileRemoteUrlKey, p2)
                                if await loadConfigFile(context, True) != 0:
                                    await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
                                    return
                                else:
                                    await context.edit(f"下载并加载配置文件成功")
                        else:
                            # 根据传入模版id更新模版配置，多个用"，"或者","隔开
                            # 判断redis是否有保存配置url

                            splitStr = "，"
                            if "," in p2:
                                splitStr = ","
                            ids = p2.split(splitStr)
                            if len(ids) > 0:
                                # 下载文件
                                configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
                                if configFileRemoteUrl:
                                    if downloadFileFromUrl(configFileRemoteUrl, configFilePath) != 0:
                                        await context.edit(f"下载配置文件异常，请确认url是否正确")
                                        return
                                    else:
                                        # 下载成功，更新对应配置
                                        if await loadConfigFile(context) != 0:
                                            await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
                                            return
                                        else:
                                            await downloadFileByIds(ids, context)
                                else:
                                    await context.edit(f"你没有订阅远程配置文件，更新个🔨")
                    else:
                        # 没传url直接更新
                        if await updateConfig(context) != 0:
                            await context.edit(f"更新配置文件异常，请确认是否订阅远程配置文件，或从远程下载的配置文件格式是否正确")
                            return
                        else:
                            await context.edit(f"从远程更新配置文件成功")
                    return
                elif p1[0] == "！" or p1[0] == "!":
                    # 加载配置
                    if exists(configFilePath):
                        if await loadConfigFile(context) != 0:
                            await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
                            return
                    txt = ""
                    if len(positions) > 0:
                        noShowList = []
                        for key in positions:
                            txt = f"{txt}，{key}"
                            if len(positions[key]) > 2:
                                noShowList.append(positions[key][2])
                        for key in noShowList:
                            txt = txt.replace(f"，{key}", "")
                        if txt != "":
                            txt = txt[1:]
                    await context.edit(f"目前已有的模版列表如下：\n{txt}")
                    return
            defaultConfig = redis.get("eat.default-config")
            if isinstance(p2, str):
                number = p2
            elif isinstance(p2, int) and p2 > 0:
                number = int(p2)
            elif not diu_round and ((isinstance(p1, int) and int(p1) > 0) or isinstance(p1, str)):
                try:
                    number = int(p1)
                except:
                    number = p1
            elif defaultConfig:
                try:
                    defaultConfig = defaultConfig.decode()
                    number = int(defaultConfig)
                except:
                    number = str(defaultConfig)
                    # 支持配置默认是倒立的头像
                    if number.startswith("."):
                        diu_round = True
                        number = number[1:]

        except:
            number = randint(1, max_number)

        # 加载配置
        if exists(configFilePath):
            if await loadConfigFile(context) != 0:
                await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
                return

        try:
            notifyStr = notifyStrArr[str(number)]
        except:
            notifyStr = "吃头像"
        await context.edit(f"正在生成 {notifyStr} 图片中 . . .")
        markImg = Image.open("plugins/eat/" + str(target_user_id) + ".jpg")
        try:
            eatImg = Image.open("plugins/eat/eat" + str(number) + ".png")
            maskImg = Image.open("plugins/eat/mask" + str(number) + ".png")
        except:
            await context.edit(f"图片模版加载出错，请检查并更新配置：{str(number)}")
            return

        if diu_round:
            markImg = markImg.rotate(180)  # 对图片进行旋转
        try:
            number = str(number)
        except:
            pass
        result = await eat_it(context, from_user_id, eatImg, maskImg, markImg, number)
        result.save('plugins/eat/eat.webp')
        target_file = await context.client.upload_file("plugins/eat/eat.webp")
        try:
            remove("plugins/eat/" + str(target_user_id) + ".jpg")
            remove("plugins/eat/" + str(target_user_id) + ".png")
            remove("plugins/eat/" + str(from_user_id) + ".jpg")
            remove("plugins/eat/" + str(from_user_id) + ".png")
            remove("plugins/eat/eat.webp")
            remove(photo)
        except:
            pass
    else:
        await context.edit("此用户未设置头像或头像对您不可见。")
        return
    if reply_to:
        try:
            await context.client.send_file(
                context.chat_id,
                target_file,
                link_preview=False,
                force_document=False,
                reply_to=reply_to
            )
            await context.delete()
            remove("plugins/eat/eat.webp")
            try:
                remove(photo)
            except:
                pass
            return
        except TypeError:
            await context.edit("此用户未设置头像或头像对您不可见。")
        except ChatSendStickersForbiddenError:
            await context.edit("此群组无法发送贴纸。")
    else:
        try:
            await context.client.send_file(
                context.chat_id,
                target_file,
                link_preview=False,
                force_document=False
            )
            await context.delete()
            remove("plugins/eat/eat.webp")
            try:
                remove(photo)
            except:
                pass
            return
        except TypeError:
            await context.edit("此用户未设置头像或头像对您不可见。")
        except ChatSendStickersForbiddenError:
            await context.edit("此群组无法发送贴纸。")
