""" Pagermaid auto-backup plugin. """
import json
import os
from datetime import datetime
from distutils.util import strtobool
from pagermaid import config, redis_status, redis, scheduler, bot
from pagermaid.utils import upload_attachment
from pagermaid.modules.backup import make_tar_gz


@scheduler.scheduled_job("cron", day="*", hour="0", minute="0", second="20", id="backup_job")
async def run_every_1_day():
    # remove mp3 , they are so big !
    for i in os.listdir("data"):
        if i.find(".mp3") != -1 or i.find(".jpg") != -1 or i.find(".flac") != -1 or i.find(".ogg") != -1:
            os.remove(f"data{os.sep}{i}")
    # backup redis
    redis_data = {}
    if redis_status():
        for k in redis.keys():
            data_type = redis.type(k)
            if data_type == b'string':
                v = redis.get(k)
                redis_data[k.decode()] = v.decode()
    with open(f"data{os.sep}redis.json", "w", encoding='utf-8') as f:
        json.dump(redis_data, f, indent=4)
    # run backup function
    if strtobool(config['log']):
        make_tar_gz(f"pagermaid_{datetime.now().date()}.tar.gz", ["data", "plugins", "config.yml"])
        await upload_attachment(f"pagermaid_{datetime.now().date()}.tar.gz", int(config['log_chatid']), None)
        os.remove(f"pagermaid_{datetime.now().date()}.tar.gz")
    else:
        make_tar_gz(f"pagermaid_backup.tar.gz", ["data", "plugins", "config.yml"])
