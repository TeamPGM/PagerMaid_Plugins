## Gemini

Google Gemini AI 插件。需要 PagerMaid-Modify 1.5.8 及以上版本。

核心功能:
- `gemini [query]`: 与模型聊天 (默认)。
- `gemini image [prompt]`: 生成或编辑图片。
- `gemini search [query]`: 使用 Gemini AI 支持的 Google 搜索。

设置:
- `gemini settings`: 显示当前配置。
- `gemini set_api_key [key]`: 设置您的 Gemini API 密钥。
- `gemini set_base_url [url]`: 设置自定义 Gemini API 基础 URL。留空以清除。
- `gemini max_tokens [number]`: 设置最大输出 token 数 (0 表示无限制)。

模型管理:
- `gemini model list`: 列出可用模型。
- `gemini model set [chat|search|image] [name]`: 设置聊天、搜索或图片模型。

提示词管理:
- `gemini prompt list`: 列出所有已保存的系统提示。
- `gemini prompt add [name] [prompt]`: 添加一个新的系统提示。
- `gemini prompt del [name]`: 删除一个系统提示。
- `gemini prompt set [chat|search] [name]`: 设置聊天或搜索的激活系统提示。

上下文管理:
- `gemini context [on|off]`: 开启或关闭对话上下文。
- `gemini context clear`: 清除对话历史。
- `gemini context show`: 显示对话历史。

Telegraph 集成:
- `gemini telegraph [on|off]`: 开启或关闭 Telegraph 集成。
- `gemini telegraph limit [number]`: 设置消息字符数超过多少时自动发送至 Telegraph (0 表示消息字数超过 Telegram 限制时发送)。
- `gemini telegraph list [page]`: 列出已创建的 Telegraph 文章。
- `gemini telegraph del [id|all]`: 删除指定的 Telegraph 文章或全部文章。
- `gemini telegraph clear`: 从列表中清除所有 Telegraph 文章记录。
