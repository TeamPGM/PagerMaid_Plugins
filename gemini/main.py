import traceback
import html
import io
import httpx
import re

from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import sqlite as db
from pagermaid.utils import alias_command, pip_install

from PIL import Image
from telethon.errors import MessageTooLongError

# Dependencies
pip_install("google-genai")
pip_install("markdown")
pip_install("telegraph[aio]")
pip_install("beautifulsoup4")
import markdown
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from telegraph import Telegraph

# --- Constants ---
DB_PREFIX = "custom.gemini."
DB_API_KEY = f"{DB_PREFIX}api_key"
DB_CHAT_MODEL = f"{DB_PREFIX}chat_model"
DB_SEARCH_MODEL = f"{DB_PREFIX}search_model"
DB_IMAGE_MODEL = f"{DB_PREFIX}image_model"
DB_CHAT_ACTIVE_PROMPT = f"{DB_PREFIX}chat_active_prompt"
DB_SEARCH_ACTIVE_PROMPT = f"{DB_PREFIX}search_active_prompt"
DB_MAX_TOKENS = f"{DB_PREFIX}max_output_tokens"
DB_PROMPTS = f"{DB_PREFIX}prompts"
DB_CONTEXT_ENABLED = f"{DB_PREFIX}context_enabled"
DB_CHAT_HISTORY = f"{DB_PREFIX}chat_history"
DB_TELEGRAPH_ENABLED = f"{DB_PREFIX}telegraph_enabled"
DB_TELEGRAPH_LIMIT = f"{DB_PREFIX}telegraph_limit"
DB_TELEGRAPH_TOKEN = f"{DB_PREFIX}telegraph_token"
DB_TELEGRAPH_POSTS = f"{DB_PREFIX}telegraph_posts"
DB_BASE_URL = f"{DB_PREFIX}base_url"

DEFAULT_CHAT_MODEL = "gemini-2.0-flash"
DEFAULT_SEARCH_MODEL = "gemini-2.0-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"
SEARCH_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
IMAGE_MODELS = ["gemini-2.0-flash-preview-image-generation"]

# --- Telegraph Setup ---

async def _get_telegraph_content(url: str) -> str | None:
    """Fetches and parses content from a Telegraph URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        article = soup.find('article')
        if article:
            return article.get_text(separator='\n', strip=True)
        return None
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None
    except Exception:
        return None

def _get_telegraph_client():
    """Creates or retrieves a Telegraph client."""
    token = db.get(DB_TELEGRAPH_TOKEN)
    if not token:
        telegraph = Telegraph()
        telegraph.create_account(short_name='PagerMaid-Gemini')
        token = telegraph.get_access_token()
        db[DB_TELEGRAPH_TOKEN] = token
    return Telegraph(access_token=token)


# --- Helper Functions ---

async def _send_usage(message: Message, command: str, usage: str):
    """Sends a formatted usage message."""
    await message.edit(f"<b>用法:</b> <code>,{alias_command('gemini')} {command} {usage}</code>", parse_mode='html')


async def _show_error(message: Message, text: str):
    """Sends a formatted error message."""
    await message.edit(f"<b>错误:</b> <code>{text}</code>", parse_mode='html')

def _censor_url(url: str) -> str:
    """Censors the domain part of a URL."""
    if not url:
        return "默认"
    return re.sub(r'(?<=//)[^/]+', '***', url)

def _get_prompt_text_for_display(message: Message, args: str) -> str:
    """Gets the primary text prompt for display purposes."""
    if args:
        return args
    reply = message.reply_to_message
    if reply and not reply.sticker and (reply.text or reply.caption):
        return reply.text or reply.caption
    return ""


async def _get_text_from_potential_telegraph(text: str, message_for_edit: Message) -> str:
    """Checks for a Telegraph URL in the text and returns its content if found, otherwise returns the original text."""
    if not text:
        return ""
    telegraph_match = re.search(r'https://telegra\.ph/[\w/-]+', text)
    if telegraph_match:
        telegraph_url = telegraph_match.group(0)
        await message_for_edit.edit("<i>正在提取 Telegraph 链接内容...</i>", parse_mode='html')
        telegraph_content = await _get_telegraph_content(telegraph_url)
        edit_text = "<i>思考中...</i>"
        await message_for_edit.edit(edit_text, parse_mode='html')
        # Fallback to using the message text itself if extraction fails
        return telegraph_content or text
    return text


async def _get_full_content(message: Message, args: str) -> list | None:
    """Gathers prompt and images from message, reply, and args."""
    content_parts = []
    text_parts = []

    # Determine which message has media
    message_with_media = None
    reply = await message.get_reply_message()
    if message.photo or (message.sticker and message.sticker.mime_type.startswith("image/")):
        message_with_media = message
    elif reply and (reply.photo or (reply.sticker and reply.sticker.mime_type.startswith("image/"))):
        message_with_media = reply

    if message_with_media:
        if db.get(DB_CONTEXT_ENABLED):
            await _show_error(message, "启用对话历史记录时不支持图片上下文。")
            return None  # Error case

        if message_with_media.file and message_with_media.file.size > 10 * 1024 * 1024:
            await _show_error(message, "图片大小超过 10MB 限制。")
            return None  # Error case

        image_bytes = await message_with_media.download_media(bytes)
        img = Image.open(io.BytesIO(image_bytes))
        content_parts.append(img)

    def _remove_gemini_footer(text: str) -> str:
        """Remove last line if it contains 'Powered by Gemini'."""
        lines = text.splitlines()
        if lines and "Powered by Gemini" in lines[-1]:
            lines.pop()
        return "\n".join(lines)

    # Gather text from reply
    if reply:
        if not reply.sticker and (reply.text or reply.caption):
            replied_text = reply.text or reply.caption
            replied_text = _remove_gemini_footer(replied_text)
            processed_text = await _get_text_from_potential_telegraph(replied_text, message)
            text_parts.append(processed_text)

    # Gather text from args
    if args:
        args = _remove_gemini_footer(args)
        processed_args = await _get_text_from_potential_telegraph(args, message)
        text_parts.append(processed_args)

    full_text = "\n".join(text_parts)

    if full_text:
        content_parts.insert(0, full_text)

    if not content_parts:
        return []  # No prompt

    return content_parts


async def _call_gemini_api(message: Message, contents: list, use_search: bool) -> str | None:
    """Calls the Gemini API and returns the response text, or None on error."""
    api_key = db.get(DB_API_KEY)
    if not api_key:
        await message.edit(f"<b>未设置 Gemini API 密钥。</b> 请使用 <code>,{alias_command('gemini')} set_api_key [your_api_key]</code> 进行设置。", parse_mode='html')
        return None

    if use_search:
        model_name = db.get(DB_SEARCH_MODEL, DEFAULT_SEARCH_MODEL)
        active_prompt_key = DB_SEARCH_ACTIVE_PROMPT
    else:
        model_name = db.get(DB_CHAT_MODEL, DEFAULT_CHAT_MODEL)
        active_prompt_key = DB_CHAT_ACTIVE_PROMPT

    max_output_tokens = db.get(DB_MAX_TOKENS, 0)

    system_prompt_name = db.get(active_prompt_key)
    prompts = db.get(DB_PROMPTS, {})
    system_prompt = "你是一个乐于助人的人工智能助手。"
    if system_prompt_name:
        system_prompt = prompts.get(system_prompt_name, system_prompt)

    try:
        base_url = db.get(DB_BASE_URL)
        headers = None
        if base_url:
            headers = {"x-goog-api-key": api_key}
        http_options = types.HttpOptions(
            base_url=base_url,
            headers=headers,
        )
        client = genai.Client(api_key=api_key, vertexai=False, http_options=http_options)
        safety_settings = [
            types.SafetySetting(category=c, threshold='BLOCK_NONE') for c in [
                'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_DANGEROUS_CONTENT',
                'HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
                'HARM_CATEGORY_CIVIC_INTEGRITY',
            ]
        ]

        tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            safety_settings=safety_settings,
            max_output_tokens=max_output_tokens if max_output_tokens > 0 else None,
            tools=tools
        )

        api_contents = contents
        if db.get(DB_CONTEXT_ENABLED) and not use_search:
            history = db.get(DB_CHAT_HISTORY, [])
            api_contents = history + contents

        response = client.models.generate_content(
            model=f"models/{model_name}",
            contents=api_contents,
            config=config,
        )

        if db.get(DB_CONTEXT_ENABLED) and not use_search:
            # contents[0] should be the text prompt
            history.append(contents[0])
            history.append(response.text)
            db[DB_CHAT_HISTORY] = history

        return response.text

    except Exception as e:
        await message.edit(f"调用 Gemini API 时出错:\n<pre><code>{html.escape(str(e))}</code></pre>", parse_mode='html')
        return None


async def _call_gemini_image_api(message: Message, contents: list) -> tuple[str | None, Image.Image | None]:
    """Calls the Gemini Image API and returns the text and image, or None on error."""
    api_key = db.get(DB_API_KEY)
    if not api_key:
        await message.edit(
            f"<b>未设置 Gemini API 密钥。</b> 请使用 <code>,{alias_command('gemini')} set_api_key [your_api_key]</code> 进行设置。",
            parse_mode='html')
        return None, None

    model_name = db.get(DB_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)

    try:
        base_url = db.get(DB_BASE_URL)
        headers = None
        if base_url:
            headers = {"x-goog-api-key": api_key}
        http_options = types.HttpOptions(
            base_url=base_url,
            headers=headers,
        )
        client = genai.Client(api_key=api_key, vertexai=False, http_options=http_options)

        config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        )

        response = client.models.generate_content(
            model=f"models/{model_name}",
            contents=contents,
            config=config,
        )

        text_response = None
        image_response = None

        for part in response.candidates[0].content.parts:
            if part.text:
                text_response = part.text
            elif part.inline_data:
                image_response = Image.open(io.BytesIO(part.inline_data.data))

        return text_response, image_response

    except Exception as e:
        await message.edit(f"调用 Gemini API 时出错:\n<pre><code>{html.escape(str(e))}</code></pre>",
                           parse_mode='html')
        return None, None

# --- Sub-command Handlers ---

async def _handle_set_api_key(message: Message, args: str):
    """处理 'set_api_key' 子命令。"""
    if not args:
        await _send_usage(message, "set_api_key", "[your_api_key]")
        return
    db[DB_API_KEY] = args
    await message.edit("<b>Gemini API 密钥已设置。</b>", parse_mode='html')


async def _handle_set_base_url(message: Message, args: str):
    """处理 'set_base_url' 子命令。"""
    if not args:
        # Clear the base_url if no argument is provided
        db[DB_BASE_URL] = None
        await message.edit("<b>Gemini 基础 URL 已清除。</b>", parse_mode='html')
        return
    db[DB_BASE_URL] = args
    await message.edit(f"<b>Gemini 基础 URL 已设置为:</b> <code>{args}</code>", parse_mode='html')


async def _handle_settings(message: Message, args: str):
    """处理 'settings' 子命令。"""
    chat_model_name = db.get(DB_CHAT_MODEL, DEFAULT_CHAT_MODEL)
    search_model_name = db.get(DB_SEARCH_MODEL, DEFAULT_SEARCH_MODEL)
    image_model_name = db.get(DB_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)
    chat_active_prompt = db.get(DB_CHAT_ACTIVE_PROMPT, "默认")
    search_active_prompt = db.get(DB_SEARCH_ACTIVE_PROMPT, "默认")
    max_tokens = db.get(DB_MAX_TOKENS, 0)
    context_enabled = db.get(DB_CONTEXT_ENABLED, False)
    telegraph_enabled = db.get(DB_TELEGRAPH_ENABLED, False)
    telegraph_limit = db.get(DB_TELEGRAPH_LIMIT, 0)
    base_url = db.get(DB_BASE_URL)
    censored_base_url = _censor_url(base_url)
    settings_text = (
        f"<b>Gemini 设置:</b>\n\n"
        f"<b>· 基础 URL:</b> <code>{censored_base_url}</code>\n"
        f"<b>· 聊天模型:</b> <code>{chat_model_name}</code>\n"
        f"<b>· 搜索模型:</b> <code>{search_model_name}</code>\n"
        f"<b>· 图片生成模型:</b> <code>{image_model_name}</code>\n"
        f"<b>· 当前聊天提示:</b> <code>{chat_active_prompt}</code>\n"
        f"<b>· 当前搜索提示:</b> <code>{search_active_prompt}</code>\n"
        f"<b>· 生成 Token 最大数量:</b> <code>{max_tokens if max_tokens > 0 else '无限制'}</code>\n"
        f"<b>· 上下文已启用:</b> <code>{context_enabled}</code>\n"
        f"<b>· Telegraph 已启用:</b> <code>{telegraph_enabled}</code>\n"
        f"<b>· Telegraph 限制:</b> <code>{telegraph_limit if telegraph_limit > 0 else '无限制'}</code>"
    )
    await message.edit(settings_text, parse_mode='html')

async def _handle_max_tokens(message: Message, args: str):
    """处理 'max_tokens' 子命令。"""
    if not args:
        await _send_usage(message, "max_tokens", "[number] (0 for unlimited)")
        return
    try:
        tokens = int(args)
        if tokens < 0:
            await message.edit("<b>最大 token 数必须为非负整数。</b>", parse_mode='html')
        else:
            db[DB_MAX_TOKENS] = tokens
            if tokens == 0:
                await message.edit("<b>最大输出 token 限制已清除 (无限制)。</b>", parse_mode='html')
            else:
                await message.edit(f"<b>最大输出 token 数已设置为 {tokens}。</b>", parse_mode='html')
    except ValueError:
        await message.edit("<b>无效的 token 数。</b>", parse_mode='html')

async def _handle_model(message: Message, args: str):
    """处理 'model' 子命令。"""
    model_args = args.split(maxsplit=2) if args else []
    action = model_args[0] if model_args else None

    if action == "set":
        if len(model_args) > 2:
            model_type = model_args[1]
            model_name = model_args[2]
            if model_type == "chat":
                db[DB_CHAT_MODEL] = model_name
                await message.edit(f"<b>Gemini 聊天模型已设置为:</b> <code>{model_name}</code>", parse_mode='html')
            elif model_type == "search":
                if model_name not in SEARCH_MODELS:
                    await message.edit(f"<b>无效的搜索模型。</b> 请从以下选项中选择: <code>{', '.join(SEARCH_MODELS)}</code>", parse_mode='html')
                    return
                db[DB_SEARCH_MODEL] = model_name
                await message.edit(f"<b>Gemini 搜索模型已设置为:</b> <code>{model_name}</code>", parse_mode='html')
            elif model_type == "image":
                if model_name not in IMAGE_MODELS:
                    await message.edit(f"<b>无效的图片模型。</b> 请从以下选项中选择: <code>{', '.join(IMAGE_MODELS)}</code>", parse_mode='html')
                    return
                db[DB_IMAGE_MODEL] = model_name
                await message.edit(f"<b>Gemini 图片模型已设置为:</b> <code>{model_name}</code>", parse_mode='html')
            else:
                await _send_usage(message, "model set", "[chat|search|image] [model_name]")
        else:
            await _send_usage(message, "model set", "[chat|search|image] [model_name]")
    elif action == "list":
        api_key = db.get(DB_API_KEY)
        if not api_key:
            await message.edit(f"<b>未设置 Gemini API 密钥。</b> 请使用 <code>,{alias_command('gemini')} set_api_key [your_api_key]</code> 进行设置。", parse_mode='html')
            return

        await message.edit("<i>正在搜索可用模型...</i>", parse_mode='html')

        try:
            base_url = db.get(DB_BASE_URL)
            headers = None
            if base_url:
                headers = {"x-goog-api-key": api_key}
            http_options = types.HttpOptions(
                base_url=base_url,
                headers=headers,
            )
            client = genai.Client(api_key=api_key, vertexai=False, http_options=http_options)
            model_list = []
            for m in client.models.list():
                model_list.append(m.name.replace("models/", ""))

            image_models_text = f"<b>可用图片模型:</b>\n<code>{', '.join(IMAGE_MODELS)}</code>"
            search_models_text = f"<b>可用搜索模型:</b>\n<code>{', '.join(SEARCH_MODELS)}</code>"
            all_models_text = f"<b>所有可用模型:</b>\n<code>{', '.join(model_list)}</code>"

            final_text = (
                f"{image_models_text}\n\n{search_models_text}\n\n{all_models_text}"
            )

            await message.edit(final_text, parse_mode='html')
        except Exception as e:
            await message.edit(f"获取模型时出错:\n<pre><code>{html.escape(str(e))}</code></pre>", parse_mode='html')
    else:
        await _send_usage(message, "model", "[set|list]")

async def _handle_prompt(message: Message, args: str):
    """处理 'prompt' 子命令。"""
    prompt_args = args.split(maxsplit=2) if args else []
    action = prompt_args[0] if prompt_args else None
    prompts = db.get(DB_PROMPTS, {})

    if action == "add":
        if len(prompt_args) > 2:
            name, text = prompt_args[1], prompt_args[2]
            prompts[name] = text
            db[DB_PROMPTS] = prompts
            await message.edit(f"<b>系统提示 '{name}' 已添加。</b>", parse_mode='html')
        else:
            await _send_usage(message, "prompt add", "[name] [prompt]")
    elif action == "del":
        if len(prompt_args) > 1:
            name = prompt_args[1]
            if name in prompts:
                del prompts[name]
                db[DB_PROMPTS] = prompts
                await message.edit(f"<b>系统提示 '{name}' 已删除。</b>", parse_mode='html')
            else:
                await message.edit(f"<b>未找到系统提示 '{name}'。</b>", parse_mode='html')
        else:
            await _send_usage(message, "prompt del", "[name]")
    elif action == "list":
        if not prompts:
            await message.edit("<b>未保存任何系统提示。</b>", parse_mode='html')
            return
        response_text = "<b>可用的系统提示:</b>\n\n"
        for name, content in prompts.items():
            escaped_content = html.escape(content)
            response_text += f"• <code>{name}</code>:\n<pre><code>{escaped_content}</code></pre>\n"
        await message.edit(response_text, parse_mode='html')
    elif action == "set":
        if len(prompt_args) > 2:
            prompt_type = prompt_args[1]
            name = prompt_args[2]
            if name not in prompts:
                await message.edit(f"<b>未找到系统提示 '{name}'。</b>", parse_mode='html')
                return
            if prompt_type == 'chat':
                db[DB_CHAT_ACTIVE_PROMPT] = name
                await message.edit(f"<b>当前聊天系统提示已设置为:</b> <code>{name}</code>", parse_mode='html')
            elif prompt_type == 'search':
                db[DB_SEARCH_ACTIVE_PROMPT] = name
                await message.edit(f"<b>当前搜索系统提示已设置为:</b> <code>{name}</code>", parse_mode='html')
            else:
                await _send_usage(message, "prompt set", "[chat|search] [name]")
        else:
            await _send_usage(message, "prompt set", "[chat|search] [name]")
    else:
        await _send_usage(message, "prompt", "[add|del|list|set]")

async def _handle_context(message: Message, args: str):
    """处理 'context' 子命令。"""
    if args == "on":
        db[DB_CONTEXT_ENABLED] = True
        await message.edit("<b>对话上下文已启用。</b>", parse_mode='html')
    elif args == "off":
        db[DB_CONTEXT_ENABLED] = False
        await message.edit("<b>对话上下文已禁用。</b>", parse_mode='html')
    elif args == "clear":
        db[DB_CHAT_HISTORY] = []
        await message.edit("<b>对话历史已清除。</b>", parse_mode='html')
    elif args == "show":
        history = db.get(DB_CHAT_HISTORY, [])
        if not history:
            await message.edit("<b>对话历史为空。</b>", parse_mode='html')
            return
        response_text = "<b>对话历史:</b>\n\n"
        for i, item in enumerate(history):
            role = "用户" if i % 2 == 0 else "模型"
            response_text += f"<b>{role}:</b>\n<pre><code>{html.escape(str(item))}</code></pre>\n"
        try:
            await message.edit(response_text, parse_mode='html')
        except MessageTooLongError:
            await _show_error(message, "历史记录太长，无法显示。")
    else:
        await _send_usage(message, "context", "[on|off|clear|show]")


async def _send_to_telegraph(title: str, content: str) -> str | None:
    """Creates a Telegraph page and returns its URL."""
    try:
        client = _get_telegraph_client()
        page = client.create_page(title=title, html_content=content)
        posts = db.get(DB_TELEGRAPH_POSTS, {})
        post_id = str(max(map(int, posts.keys()), default=0) + 1)
        posts[post_id] = {"path": page['path'], "title": title}
        db[DB_TELEGRAPH_POSTS] = posts
        return page['url']
    except Exception:
        return None


async def _handle_telegraph(message: Message, args: str):
    """处理 'telegraph' 子命令。"""
    parts = args.split(maxsplit=1)
    action = parts[0] if parts else None
    action_args = parts[1] if len(parts) > 1 else ""

    if action == "on":
        db[DB_TELEGRAPH_ENABLED] = True
        await message.edit("<b>Telegraph 集成已启用。</b>", parse_mode='html')
    elif action == "off":
        db[DB_TELEGRAPH_ENABLED] = False
        await message.edit("<b>Telegraph 集成已禁用。</b>", parse_mode='html')
    elif action == "limit":
        if not action_args:
            await _send_usage(message, "telegraph limit", "[number]")
            return
        try:
            limit = int(action_args)
            if limit < 0:
                await message.edit("<b>限制必须为非负整数。</b>", parse_mode='html')
            else:
                db[DB_TELEGRAPH_LIMIT] = limit
                await message.edit(f"<b>Telegraph 字符限制已设置为 {limit}。</b>", parse_mode='html')
        except ValueError:
            await message.edit("<b>无效的限制数。</b>", parse_mode='html')
    elif action == "list":
        posts = db.get(DB_TELEGRAPH_POSTS, {})
        if not posts:
            await message.edit("<b>尚未创建 Telegraph 文章。</b>", parse_mode='html')
            return

        # Sort posts by ID in descending order
        sorted_posts = sorted(posts.items(), key=lambda item: int(item[0]), reverse=True)

        # Pagination
        page = 1
        if action_args.strip():
            try:
                page = int(action_args.strip())
            except ValueError:
                page = 1

        page_size = 30
        total_posts = len(sorted_posts)
        total_pages = (total_posts + page_size - 1) // page_size or 1

        if page < 1 or page > total_pages:
            await message.edit(f"<b>无效的页码。页码必须在 1 到 {total_pages} 之间。</b>", parse_mode='html')
            return

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_posts = sorted_posts[start_index:end_index]

        text = f"<b>已创建的 Telegraph 文章 (第 {page}/{total_pages} 页):</b>\n\n"
        for post_id, data in paginated_posts:
            text += f"• <code>{post_id}</code>: <a href='https://telegra.ph/{data['path']}'>{html.escape(data['title'])}</a>\n"

        if total_pages > 1:
            text += f"\n使用 <code>,{alias_command('gemini')} telegraph list [page]</code> 查看其他页面。"

        await message.edit(text, parse_mode='html', link_preview=False)
    elif action == "del":
        if action_args == "all":
            await message.edit("<i>正在删除所有 Telegraph 文章并创建新身份...</i>", parse_mode='html')
            posts = db.get(DB_TELEGRAPH_POSTS, {})
            if not posts:
                db[DB_TELEGRAPH_TOKEN] = None
                _get_telegraph_client()
                await message.edit("<b>没有可删除的 Telegraph 文章。已创建新的 Telegraph 身份。</b>", parse_mode='html')
                return

            client = _get_telegraph_client()
            errors = 0
            for post_id, data in list(posts.items()):
                try:
                    client.edit_page(
                        path=data['path'],
                        title="[已删除]",
                        html_content="<p>本文已被删除。</p>"
                    )
                except Exception:
                    errors += 1

            db[DB_TELEGRAPH_POSTS] = {}
            db[DB_TELEGRAPH_TOKEN] = None
            _get_telegraph_client()

            if errors > 0:
                await message.edit(
                    f"<b>列表中的所有 Telegraph 文章均已清除。已创建新的 Telegraph 身份。</b>\n"
                    f"({errors} 篇文章无法从 telegra.ph 删除)", parse_mode='html')
            else:
                await message.edit("<b>所有 Telegraph 文章均已删除，并已创建新的 Telegraph 身份。</b>",
                                   parse_mode='html')
            return

        id_to_delete = action_args
        reply = await message.get_reply_message()

        if not id_to_delete and reply and (reply.text or reply.caption):
            text_to_check = reply.text or reply.caption
            telegraph_match = re.search(r'https://telegra\.ph/([\w/-]+)', text_to_check)
            if telegraph_match:
                path_to_delete = telegraph_match.group(1)
                posts = db.get(DB_TELEGRAPH_POSTS, {})
                for post_id, data in posts.items():
                    if data['path'] == path_to_delete:
                        id_to_delete = post_id
                        break
                if not id_to_delete:
                    await _show_error(message, "在数据库中找不到此 Telegraph 文章。")
                    return

        if not id_to_delete:
            await _send_usage(message, "telegraph", "[on|off|limit|list [page]|del [id|all]|clear]")
            return

        posts = db.get(DB_TELEGRAPH_POSTS, {})
        if id_to_delete in posts:
            post_to_delete = posts[id_to_delete]
            try:
                client = _get_telegraph_client()
                client.edit_page(
                    path=post_to_delete['path'],
                    title="[已删除]",
                    html_content="<p>本文已被删除。</p>"
                )
                del posts[id_to_delete]
                db[DB_TELEGRAPH_POSTS] = posts
                await message.edit(
                    f"<b>Telegraph 文章 <code>{id_to_delete}</code> 已从 Telegraph 删除并从列表中移除。</b>",
                    parse_mode='html')
            except Exception as e:
                await _show_error(message, f"无法从 Telegraph 删除文章: {e}")
        else:
            await message.edit(f"<b>未找到 ID 为 <code>{id_to_delete}</code> 的 Telegraph 文章。</b>",
                               parse_mode='html')
    elif action == "clear":
        db[DB_TELEGRAPH_POSTS] = {}
        await message.edit("<b>列表中的所有 Telegraph 文章均已清除。</b>", parse_mode='html')
    else:
        await _send_usage(message, "telegraph", "[on|off|limit|list [page]|del [id|all]|clear]")


async def _send_response(message: Message, prompt_text: str, html_output: str, powered_by: str):
    """Formats and sends the final response, handling Telegraph for long messages."""
    # Final message construction
    formatted_response = f"🤖<b>回复:</b>\n<blockquote>{html_output}</blockquote>"
    if prompt_text:
        question_text = f"👤<b>提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>"
        final_text = f"{question_text}\n{formatted_response}\n<i>{powered_by}</i>"
    else:
        final_text = f"{formatted_response}\n<i>{powered_by}</i>"

    telegraph_enabled = db.get(DB_TELEGRAPH_ENABLED)
    telegraph_limit = db.get(DB_TELEGRAPH_LIMIT, 0)

    # Check for character limit before trying to send the message
    if telegraph_enabled and telegraph_limit > 0 and len(final_text) > telegraph_limit:
        if prompt_text:
            title = (prompt_text[:15] + '...') if len(prompt_text) > 18 else prompt_text
        else:
            title = "Gemini 回复"
        url = await _send_to_telegraph(title, html_output)
        if url:
            telegraph_link_text = (f"🤖<b>回复:</b>\n"
                                   f"<b>回复超过 {telegraph_limit} 字符，已上传到 Telegraph:</b>\n {url}")
            if prompt_text:
                question_text = f"👤<b>提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>"
                final_telegraph_text = f"{question_text}\n{telegraph_link_text}\n<i>{powered_by}</i>"
            else:
                final_telegraph_text = f"{telegraph_link_text}\n<i>{powered_by}</i>"
            await message.edit(final_telegraph_text, parse_mode='html', link_preview=True)
        else:
            await _show_error(message, "输出超过字符限制，上传到 Telegraph 失败。")
        return

    try:
        await message.edit(final_text, parse_mode='html', link_preview=False)
    except MessageTooLongError:
        if telegraph_enabled:
            if prompt_text:
                title = f"{(prompt_text[:15] + '...') if len(prompt_text) > 18 else prompt_text}"
            else:
                title = "Gemini 回复"
            url = await _send_to_telegraph(title, html_output)
            if url:
                telegraph_link_text = (f"<b>回复超过 Telegram 消息最大字符数，已上传到 Telegraph:</b>\n {url}")
                response_text = (f"🤖<b>回复:</b>\n"
                                 f"{telegraph_link_text}\n<i>{powered_by}</i>")
                if prompt_text:
                    question_text = f"👤<b>提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>"
                    final_telegraph_text = f"{question_text}\n{response_text}"
                else:
                    final_telegraph_text = telegraph_link_text
                await message.edit(final_telegraph_text, parse_mode='html', link_preview=True)
            else:
                await _show_error(message, "输出过长，上传到 Telegraph 失败。")
        else:
            await _show_error(message, "输出过长。启用 Telegraph 集成以链接形式发送。")


async def _execute_gemini_request(message: Message, args: str, use_search: bool):
    """聊天和搜索请求的通用处理程序。"""
    if use_search:
        edit_text = "<i>正在搜索...</i>"
        usage_cmd = "search"
        powered_by = "由 Gemini 与 Google 搜索强力驱动"
    else:
        edit_text = "<i>思考中...</i>"
        usage_cmd = ""
        powered_by = "由 Gemini 强力驱动"

    await message.edit(edit_text, parse_mode='html')

    contents = await _get_full_content(message, args)
    if contents is None:
        return
    if not contents:
        await _send_usage(message, usage_cmd, "[query] or reply to a message.")
        return

    output_text = await _call_gemini_api(message, contents, use_search=use_search)
    if output_text is None:
        return

    html_output = markdown.markdown(output_text)
    prompt_text = _get_prompt_text_for_display(message, args)
    await _send_response(message, prompt_text, html_output, powered_by)


async def _handle_search(message: Message, args: str):
    """处理搜索功能。"""
    await _execute_gemini_request(message, args, use_search=True)


async def _handle_chat(message: Message, args: str):
    """处理聊天功能 (默认操作)。"""
    await _execute_gemini_request(message, args, use_search=False)


async def _handle_image(message: Message, args: str):
    """处理图片生成和编辑功能。"""
    await message.edit("<i>正在生成图片...</i>", parse_mode='html')

    contents = await _get_full_content(message, args)
    if contents is None:
        return
    if not contents:
        await _send_usage(message, "image", "[prompt] (reply to an image to edit)")
        return

    text_response, image_response = await _call_gemini_image_api(message, contents)

    if image_response:
        # Create a BytesIO object to hold the image data
        image_stream = io.BytesIO()
        image_response.save(image_stream, format='PNG')
        image_stream.seek(0)  # Rewind the stream to the beginning
        image_stream.name = 'gemini.png'


        prompt_text = _get_prompt_text_for_display(message, args)
        powered_by = "由 Gemini 图片生成强力驱动"

        # Build caption
        caption_parts = []
        if prompt_text:
            caption_parts.append(f"👤<b>提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>\n")
        if text_response:
            caption_parts.append(f"🤖<b>回复:</b>\n<blockquote>{html.escape(text_response)}</blockquote>")
        caption_parts.append(f"<i>{powered_by}</i>")
        final_caption = "".join(caption_parts)

        await message.client.send_file(
            message.chat_id,
            file=image_stream,
            caption=final_caption,
            parse_mode='html',
            link_preview=False,
            reply_to=message.id
        )
        await message.edit("图片已生成")

    elif text_response:
        # If only text is returned, show it as an error/info
        await _show_error(message, f"模型返回了文本而非图片: {text_response}")
    else:
        # This case is handled by the error in _call_gemini_image_api, but as a fallback:
        await _show_error(message, "生成图片失败，且未返回任何文本回复。")


@listener(
    command="gemini",
    description="""
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
""",
    parameters="[命令] [参数]"
)
async def gemini(message: Message):
    """gemini 插件的主处理程序，分派给子处理程序。"""
    parts = message.arguments.split(maxsplit=1)
    sub_command = parts[0] if parts else None
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "set_api_key": _handle_set_api_key,
        "set_base_url": _handle_set_base_url,
        "settings": _handle_settings,
        "max_tokens": _handle_max_tokens,
        "model": _handle_model,
        "prompt": _handle_prompt,
        "search": _handle_search,
        "image": _handle_image,
        "context": _handle_context,
        "telegraph": _handle_telegraph,
    }

    try:
        if sub_command in handlers:
            await handlers[sub_command](message, args)
        else:
            # Default action is chat
            await _handle_chat(message, message.arguments)
    except Exception:
        exc_text = traceback.format_exc()
        await message.edit(f"发生意外错误:\n<pre><code>{html.escape(exc_text)}</code></pre>", parse_mode='html')
