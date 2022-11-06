import json, time, sys
from httpx import get, post

token = str(sys.argv[1])
main = json.loads(get("https://api.github.com/repos/TeamPGM/PagerMaid_Plugins/commits/master").content)
text = "#更新日志 #" + main['commit']['author']['name'].replace('_', '') + \
       ' \n\n🔨 [' + main['sha'][0:7] + '](https://github.com/TeamPGM/PagerMaid_Plugins/commit/' + \
       main['sha'] + '): ' + main['commit']['message']
push_content = {'chat_id': '-1001441461877', 'disable_web_page_preview': 'True', 'parse_mode': 'markdown',
                'text': text}
push_content['message_thread_id'] = 1027828
url = 'https://api.telegram.org/bot' + token + '/sendMessage'
try:
    main_req = post(url, data=push_content)
except:
    pass
push_content['chat_id'] = '-1001319957857'
del push_content['message_thread_id']
time.sleep(1)
try:
    main_req = post(url, data=push_content)
except:
    pass
print(main['sha'] + " ok！")
