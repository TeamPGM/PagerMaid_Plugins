from pagermaid.listener import listener
from pagermaid.utils import alias_command, obtain_message, pip_install

pip_install("covid")

from covid import Covid


@listener(is_plugin=True, outgoing=True, command=alias_command("covid-en"),
          description="获取新冠疫情信息。（国家版）",
          parameters="<英文国家名>")
async def covid_en(context):
    await context.edit("正在获取中。。。")
    try:
        country = await obtain_message(context)
    except ValueError:
        country = "World"
    covid_ = Covid(source="worldometers")
    try:
        country_data = covid_.get_status_by_country_name(country)
    except ValueError:
        return await context.edit("[covid-en] 国家名称不正确 **[Worldometer]**(https://www.worldometers.info/coronavirus)")
    if country_data:
        if country == "World":
            country_data['total_tests'] = "未知"
        output_text = f"`⚠️累计确诊：{country_data['confirmed']} (+{country_data['new_cases']})`\n"
        output_text += f"`☢️现存确诊：{country_data['active']}`\n"
        output_text += f"`🤕重症：{country_data['critical']}`\n"
        output_text += f"`😟新增死亡：{country_data['new_deaths']}`\n\n"
        output_text += f"`⚰️累计死亡：{country_data['deaths']} (+{country_data['new_deaths']})`\n"
        output_text += f"`😔新增确诊：{country_data['new_cases']}`\n"
        output_text += f"`😇累计治愈：{country_data['recovered']}`\n"
        output_text += f"`🧪累计检查：{country_data['total_tests']}`\n\n"
        if country == "World":
            output_text += f"**数据由 [Worldometer]**(https://www.worldometers.info/coronavirus) **提供**"
            country = "全球"
        else:
            output_text += f"**数据由 [Worldometer]**(https://www.worldometers.info/coronavirus/country/{country}) **提供**"
            country += " "
    else:
        output_text = "没有找到此国家的数据！"

    await context.edit(f"**{country}新冠肺炎疫情情况**\n\n{output_text}")
