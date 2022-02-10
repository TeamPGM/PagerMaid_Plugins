""" PagerMaid Plugin to provide a dictionary lookup. """

from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command, pip_install, obtain_message, client
from telethon.events.newmessage import NewMessage

pip_install("PyDictionary")

from PyDictionary import PyDictionary

dictionary = PyDictionary()


@listener(is_plugin=True, outgoing=True, command=alias_command("dictionary"),
          description="查询英语单词的意思")
async def get_word_mean(context: NewMessage.Event) -> None:
    """ Look up a word in the dictionary. """
    try:
        word = await obtain_message(context)
    except ValueError:
        await context.edit(f"[dictionary] 使用方法：`-{alias_command('dictionary')} <单词>`")
        return

    result = dictionary.meaning(word)
    output = f"**Word :** __{word}__\n\n"
    if result:
        try:
            for a, b in result.items():
                output += f"**{a}**\n"
                for i in b:
                    output += f"☞__{i}__\n"
            await context.edit(output)
        except Exception:
            await context.edit("[dictionary] 无法查询到单词的意思")
    else:
        await context.edit("[dictionary] 无法查询到单词的意思")


@listener(is_plugin=True, outgoing=True, command=alias_command("urbandictionary"),
          description="解释英语俚语词汇")
async def get_urban_mean(context: NewMessage.Event) -> None:
    """ To fetch meaning of the given word from urban dictionary. """
    try:
        word = await obtain_message(context)
    except ValueError:
        await context.edit(f"[urbandictionary] 使用方法：`-{alias_command('urbandictionary')} <单词>`")
        return

    response = await client.get(f"https://api.urbandictionary.com/v0/define?term={word}")
    try:
        response = response.json()
    except:
        await context.edit("[urbandictionary] API 接口无法访问")
        return

    if len(response["list"]) == 0:
        await context.edit("[urbandictionary] 无法查询到单词的意思")
        return

    word = response["list"][0]["word"]
    definition = response["list"][0]["definition"]
    example = response["list"][0]["example"]
    result = f"**Word :** __{word}__\n\n" \
             f"**Meaning:**\n" \
             f"`{definition}`\n\n" \
             f"**Example:**\n" \
             f"`{example}`"
    await context.edit(result)
