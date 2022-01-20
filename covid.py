""" https://github.com/Zeta-qixi/nonebot-plugin-covid19-news """

import json
from typing import Dict
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import alias_command, obtain_message, client

POLICY_ID = {}


class Area:
    def __init__(self, data):
        self.name = data['name']
        self.today = data['today']
        self.total = data['total']
        self.grade = data['total'].get('grade', '风险未确认')
        self.children = data.get('children', None)

    @property
    async def policy(self):
        return await get_policy(POLICY_ID.get(self.name))

    @property
    def main_info(self):
        return f"**{self.name} 新冠肺炎疫情情况**  ({self.grade})\n\n" \
               f"`😔新增确诊：{self.today['confirm']}`\n" \
               f"`☢️现存确诊：{self.total['nowConfirm']}`"


class AreaList(Dict):
    def add(self, data):
        self[data.name] = data


class NewsData:
    def __init__(self):
        self.data = {}
        self.time = ''
        self.update_data()

    async def update_data(self):
        url = "https://view.inews.qq.com/g2/getOnsInfo?name=disease_h5"
        res = (await client.get(url)).json()

        if res['ret'] != 0:
            return
        data = json.loads(res['data'])

        if data['lastUpdateTime'] != self.time:

            self.time = data['lastUpdateTime']
            self.data = AreaList()

            def get_Data(data_):

                if isinstance(data_, list):
                    for i in data_:
                        get_Data(i)

                if isinstance(data_, dict):
                    area_ = data_.get('children')
                    if area_:
                        get_Data(area_)

                    self.data.add(Area(data_))  # noqa

            get_Data(data['areaTree'][0])
            return


async def set_pid():
    url_city_list = 'https://r.inews.qq.com/api/trackmap/citylist?'
    resp = await client.get(url_city_list)
    res = resp.json()

    for province in res['result']:
        cities = province.get('list')
        if cities:
            for city in cities:
                cid = city['id']
                name = city['name']
                POLICY_ID[name] = cid


async def get_policy(uid):
    url_get_policy = f"https://r.inews.qq.com/api/trackmap/citypolicy?&city_id={uid}"
    resp = await client.get(url_get_policy)
    res_ = resp.json()
    if res_['message'] != 'success':
        return "数据获取失败！"
    try:
        data = res_['result']['data'][0]
    except IndexError:
        return "暂无政策信息"

    # data['leave_policy_date']
    # data['leave_policy']

    # data['back_policy_date']
    # data['back_policy']

    # data['poi_list']  # 风险区域

    msg = f"出行({data['leave_policy_date']})\n{data['leave_policy']}\n\
------\n\
进入({data['back_policy_date']})\n{data['back_policy']}"

    return msg


NewsBot = NewsData()


@listener(is_plugin=True, outgoing=True, command=alias_command("covid"),
          description="获取新冠疫情信息。",
          parameters="<地区>")
async def covid_info(context):
    global POLICY_ID, NewsBot
    await context.edit("正在获取中。。。")
    if not POLICY_ID:
        await set_pid()
    await NewsBot.update_data()

    try:
        city = await obtain_message(context)
    except ValueError:
        return await context.edit("[covid] 无法获取城市名！")
    zc = False
    if city.find("政策") != -1:
        zc = True
        city = city.replace("政策", "")
    city = NewsBot.data.get(city)
    if city:
        policy = "Tips: 查询出行政策可加上 `政策`"
        if zc:
            policy = await city.policy
        await context.edit(f"{city.main_info}\n\n{policy}")
    else:
        await context.edit("[covid] 只限查询国内城市或你地理没学好。")
