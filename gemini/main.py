import traceback
import html
import io
import httpx
import re
import importlib
import os
import asyncio

from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.services import sqlite as db
from pagermaid.utils import alias_command, pip_install

from PIL import Image
from telethon.errors import MessageTooLongError, MessageEmptyError
from telethon.extensions import html as tg_html
from telethon.tl.types import (
    MessageEntityBlockquote, MessageEntityItalic, MessageEntityBold
)

# Dependencies
dependencies = {
    "google.genai": "google-genai",
    "markdown": "markdown",
    "telegraph": "telegraph",
    "bs4": "beautifulsoup4",
    "emoji": "emoji",
}

for module, package in dependencies.items():
    try:
        importlib.import_module(module)
    except ModuleNotFoundError:
        pip_install(package)

import markdown
import emoji
from google import genai
from google.genai import types
from telegraph import Telegraph
from bs4 import BeautifulSoup


class Config:
    """Centralized configuration for the Gemini plugin."""
    # --- Constants ---
    PREFIX = "custom.gemini."
    # DB Keys
    API_KEY = f"{PREFIX}api_key"
    CHAT_MODEL = f"{PREFIX}chat_model"
    SEARCH_MODEL = f"{PREFIX}search_model"
    IMAGE_MODEL = f"{PREFIX}image_model"
    TTS_MODEL = f"{PREFIX}tts_model"
    TTS_VOICE = f"{PREFIX}tts_voice"
    CHAT_ACTIVE_PROMPT = f"{PREFIX}chat_active_prompt"
    SEARCH_ACTIVE_PROMPT = f"{PREFIX}search_active_prompt"
    TTS_ACTIVE_PROMPT = f"{PREFIX}tts_active_prompt"
    MAX_TOKENS = f"{PREFIX}max_output_tokens"
    PROMPTS = f"{PREFIX}prompts"
    CONTEXT_ENABLED = f"{PREFIX}context_enabled"
    CHAT_HISTORY = f"{PREFIX}chat_history"
    TELEGRAPH_ENABLED = f"{PREFIX}telegraph_enabled"
    TELEGRAPH_LIMIT = f"{PREFIX}telegraph_limit"
    TELEGRAPH_TOKEN = f"{PREFIX}telegraph_token"
    TELEGRAPH_POSTS = f"{PREFIX}telegraph_posts"
    COLLAPSIBLE_QUOTE_ENABLED = f"{PREFIX}collapsible_quote_enabled"
    BASE_URL = f"{PREFIX}base_url"

    # Defaults
    DEFAULT_CHAT_MODEL = "gemini-2.0-flash"
    DEFAULT_SEARCH_MODEL = "gemini-2.0-flash"
    DEFAULT_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"
    DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
    DEFAULT_TTS_VOICE = "Laomedeia"

    # Model Lists
    SEARCH_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    IMAGE_MODELS = ["gemini-2.0-flash-preview-image-generation"]
    TTS_MODELS = ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]


# --- Telegraph Setup ---

async def _get_telegraph_content(url: str) -> str | None:
    """Fetches and parses content from a Telegraph URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            article = soup.find('article')
            return article.get_text(separator='\n', strip=True) if article else None
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None
    except Exception:
        return None


def _format_text_for_telegram(text: str) -> str:
    """Formats markdown text to HTML suitable for Telegram."""
    html_output = markdown.markdown(text, extensions=['fenced_code'])
    soup = BeautifulSoup(html_output, "html.parser")
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        tag.name = 'b'
        tag.insert_after(BeautifulSoup("<br>", "html.parser"))
    return str(soup)


def _get_telegraph_client():
    """Creates or retrieves a Telegraph client."""
    token = db.get(Config.TELEGRAPH_TOKEN)
    if not token:
        telegraph = Telegraph()
        telegraph.create_account(short_name='PagerMaid-Gemini')
        token = telegraph.get_access_token()
        db[Config.TELEGRAPH_TOKEN] = token
    return Telegraph(access_token=token)


# --- Helper Functions ---

def _sanitize_html_for_telegraph(html_content: str) -> str:
    """Sanitizes HTML to prevent invalid tag errors from Telegraph."""
    ALLOWED_TAGS = {
        'a', 'aside', 'b', 'blockquote', 'br', 'code', 'em', 'figcaption',
        'figure', 'h3', 'h4', 'hr', 'i', 'iframe', 'img', 'li', 'ol', 'p',
        'pre', 's', 'strong', 'u', 'ul', 'video'
    }
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
    return str(soup)


async def _send_usage(message: Message, command: str, usage: str):
    """Sends a formatted usage message."""
    await message.edit(f"<b>用法:</b> <code>,{alias_command('gemini')} {command} {usage}</code>", parse_mode='html')


async def _show_error(message: Message, text: str):
    """Sends a formatted error message."""
    await message.edit(f"<b>错误:</b> <code>{text}</code>", parse_mode='html')


def _censor_url(url: str) -> str:
    """Censors the domain part of a URL."""
    return re.sub(r'(?<=//)[^/]+', '***', url) if url else "默认"


def _get_utf16_length(text: str) -> int:
    """Calculates the length of a string in UTF-16 code units."""
    return len(text.encode('utf-16-le')) // 2


def _remove_gemini_footer(text: str) -> str:
    """Removes the 'Powered by Gemini' footer from text."""
    lines = text.splitlines()
    if lines and "Powered by Gemini" in lines[-1]:
        lines.pop()
    return "\n".join(lines)


async def _get_prompt_text_for_display(message: Message, args: str) -> str:
    """Gets the primary text prompt for display purposes, prioritizing args."""
    if args:
        return _remove_gemini_footer(args)

    reply = await message.get_reply_message()
    if reply and not reply.sticker and reply.text:
        return _remove_gemini_footer(reply.text)

    return ""


async def _get_text_from_potential_telegraph(text: str, message_for_edit: Message) -> str:
    """Extracts content from a Telegraph URL if present, otherwise returns original text."""
    if not text:
        return ""
    if match := re.search(r'https://telegra\.ph/([\w/-]+)', text):
        await message_for_edit.edit("正在提取 Telegraph 链接内容...", parse_mode='html')
        content = await _get_telegraph_content(match.group(0))
        await message_for_edit.edit("💬 思考中...", parse_mode='html')
        return content or text
    return text


async def _get_full_content(message: Message, args: str) -> list | None:
    """Gathers prompt and media from message, reply, and args."""
    content_parts, text_parts = [], []
    reply = await message.get_reply_message()

    # Determine which message has media, prioritizing the current message.
    message_with_media = None
    if message.media and not message.web_preview:
        message_with_media = message
    elif reply and reply.media and not reply.web_preview:
        message_with_media = reply

    if message_with_media:
        if db.get(Config.CONTEXT_ENABLED):
            await _show_error(message, "启用对话历史记录时不支持文件上下文。")
            return None

        if message_with_media.file and message_with_media.file.size:
            if message_with_media.file.size > 19.5 * 1024 * 1024:
                await _show_error(message, "文件大小超过 19.5MB 限制。")
                return None

            media_bytes = await message_with_media.download_media(bytes)
            mime_type = message_with_media.file.mime_type

            if message_with_media.photo or (
                    hasattr(message_with_media, 'sticker') and message_with_media.sticker and mime_type and mime_type.startswith(
                "image/")):
                content_parts.append(Image.open(io.BytesIO(media_bytes)))
            elif mime_type:
                content_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_bytes)))

    if reply and not reply.sticker and reply.text:
        replied_text = _remove_gemini_footer(reply.text)
        text_parts.append(await _get_text_from_potential_telegraph(replied_text, message))
    if args:
        processed_args = _remove_gemini_footer(args)
        text_parts.append(await _get_text_from_potential_telegraph(processed_args, message))

    if full_text := "\n".join(text_parts):
        content_parts.insert(0, full_text)
    return content_parts or []


async def _handle_gemini_exception(message: Message, e: Exception, api_name: str = "Gemini API"):
    """Handles common exceptions from the Gemini API."""
    error_str = str(e)
    if "429" in error_str and "ResourceExhausted" in error_str:
        await message.edit(f"<b>调用 {api_name} 已达到速率限制。</b>\n<pre><code>{html.escape(error_str)}</code></pre>", parse_mode='html')
    else:
        await message.edit(f"调用 {api_name} 时出错:\n<pre><code>{html.escape(error_str)}</code></pre>", parse_mode='html')


async def _get_gemini_client(message: Message) -> genai.Client | None:
    """Initializes and returns a Gemini client, handling API key and base URL."""
    api_key = db.get(Config.API_KEY)
    if not api_key:
        await message.edit(
            f"<b>未设置 Gemini API 密钥。</b> 请使用 <code>,{alias_command('gemini')} set_api_key [your_api_key]</code> 进行设置。",
            parse_mode='html')
        return None
    base_url = db.get(Config.BASE_URL)
    headers = {"x-goog-api-key": api_key} if base_url else None
    http_options = types.HttpOptions(base_url=base_url, headers=headers)
    return genai.Client(api_key=api_key, vertexai=False, http_options=http_options)


async def _call_gemini_api(message: Message, contents: list, use_search: bool) -> str | None:
    """Calls the Gemini API in a non-blocking way and returns the response text, or None on error."""
    client = await _get_gemini_client(message)
    if not client:
        return None

    model_name = db.get(Config.SEARCH_MODEL if use_search else Config.CHAT_MODEL,
                        Config.DEFAULT_SEARCH_MODEL if use_search else Config.DEFAULT_CHAT_MODEL)
    active_prompt_key = Config.SEARCH_ACTIVE_PROMPT if use_search else Config.CHAT_ACTIVE_PROMPT
    system_prompt_name = db.get(active_prompt_key)
    prompts = db.get(Config.PROMPTS, {})
    system_prompt = prompts.get(system_prompt_name, "你是一个乐于助人的人工智能助手。") if system_prompt_name else "你是一个乐于助人的人工智能助手。"
    api_contents = db.get(Config.CHAT_HISTORY, []) + contents if db.get(Config.CONTEXT_ENABLED) and not use_search else contents

    def blocking_api_call():
        safety_settings = [types.SafetySetting(category=c, threshold='BLOCK_NONE') for c in
                           ['HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_DANGEROUS_CONTENT',
                            'HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            'HARM_CATEGORY_CIVIC_INTEGRITY']]
        max_tokens = db.get(Config.MAX_TOKENS, 0)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            safety_settings=safety_settings,
            max_output_tokens=max_tokens if max_tokens > 0 else None,
            tools=[types.Tool(google_search=types.GoogleSearch())] if use_search else None
        )
        return client.models.generate_content(model=f"models/{model_name}", contents=api_contents, config=config)

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, blocking_api_call)

        if db.get(Config.CONTEXT_ENABLED) and not use_search:
            history = db.get(Config.CHAT_HISTORY, [])
            history.extend([contents[0], response.text])
            db[Config.CHAT_HISTORY] = history
        return response.text
    except Exception as e:
        await _handle_gemini_exception(message, e)
        return None


async def _call_gemini_image_api(message: Message, contents: list) -> tuple[str | None, Image.Image | None]:
    """Calls the Gemini Image API and returns the text and image, or None on error."""
    client = await _get_gemini_client(message)
    if not client:
        return None, None
    model_name = db.get(Config.IMAGE_MODEL, Config.DEFAULT_IMAGE_MODEL)
    try:
        config = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
        response = client.models.generate_content(model=f"models/{model_name}", contents=contents, config=config)
        text_response, image_response = None, None
        for part in response.candidates[0].content.parts:
            if part.text:
                text_response = part.text
            elif part.inline_data:
                image_response = Image.open(io.BytesIO(part.inline_data.data))
        return text_response, image_response
    except Exception as e:
        await _handle_gemini_exception(message, e)
        return None, None


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    """Parses bits per sample and rate from an audio MIME type string."""
    params = {"bits_per_sample": 16, "rate": 24000}
    for part in mime_type.split(";"):
        part = part.strip()
        if part.lower().startswith("rate="):
            try:
                params["rate"] = int(part.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif part.startswith("audio/L"):
            try:
                params["bits_per_sample"] = int(part.split("L", 1)[1])
            except (ValueError, IndexError):
                pass
    return params


async def _call_gemini_tts_api(message: Message, text: str) -> tuple[str | None, str | None]:
    """Calls the Gemini TTS API and returns the path to the raw audio file and its mime type."""
    client = await _get_gemini_client(message)
    if not client:
        return None, None

    def blocking_tts_call():
        # Sanitize input text by stripping markdown and whitespace
        # Convert markdown to HTML, then extract plain text to feed to the TTS engine.
        html_content = markdown.markdown(text)
        soup = BeautifulSoup(html_content, 'html.parser')
        clean_text = soup.get_text()

        # Filter out emoji characters by replacing them with a space
        clean_text = emoji.replace_emoji(clean_text, replace=' ')
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if not clean_text:
            raise ValueError("要转换为语音的文本为空。")

        model_name = db.get(Config.TTS_MODEL, Config.DEFAULT_TTS_MODEL)
        token_count_response = client.models.count_tokens(model=f"models/{model_name}", contents=[clean_text])
        if token_count_response.total_tokens > 1000:
            raise ValueError(f"TOKEN_LIMIT_EXCEEDED:{token_count_response.total_tokens}")

        voice_name = db.get(Config.TTS_VOICE, Config.DEFAULT_TTS_VOICE)
        config = types.GenerateContentConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name))
            ),
        )
        stream = client.models.generate_content_stream(
            model=f"models/{model_name}",
            contents=[clean_text],
            config=config
        )
        audio_data, audio_mime_type = bytearray(), None
        for chunk in stream:
            if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts and \
                    chunk.candidates[0].content.parts[0].inline_data and chunk.candidates[0].content.parts[0].inline_data.data:
                inline_data = chunk.candidates[0].content.parts[0].inline_data
                if not audio_mime_type:
                    audio_mime_type = inline_data.mime_type
                audio_data.extend(inline_data.data)
        return audio_data, audio_mime_type

    try:
        # We run the text cleaning and the API call inside the same executor
        # to ensure any errors during text processing are caught.
        loop = asyncio.get_running_loop()
        audio_data, audio_mime_type = await loop.run_in_executor(None, blocking_tts_call)

        if not audio_data:
            await message.edit("模型未返回任何音频数据。", parse_mode='html')
            return None, None

        output_file_path = f"gemini_tts_{message.id}.raw"
        with open(output_file_path, "wb") as f:
            f.write(audio_data)
        return output_file_path, audio_mime_type
    except ValueError as e:
        if str(e).startswith("TOKEN_LIMIT_EXCEEDED"):
            raise e
        await message.edit(f"输入文本处理失败: {e}", parse_mode='html')
        return None, None
    except Exception as e:
        await _handle_gemini_exception(message, e, api_name="Gemini TTS API")
        return None, None


# --- Sub-command Handlers ---

async def _handle_set_api_key(message: Message, args: str):
    if not args:
        await _send_usage(message, "set_api_key", "[your_api_key]")
        return
    db[Config.API_KEY] = args
    await message.edit("<b>Gemini API 密钥已设置。</b>", parse_mode='html')


async def _handle_set_base_url(message: Message, args: str):
    if not args:
        db[Config.BASE_URL] = None
        await message.edit("<b>Gemini 基础 URL 已清除。</b>", parse_mode='html')
    else:
        db[Config.BASE_URL] = args
        await message.edit(f"<b>Gemini 基础 URL 已设置为:</b> <code>{args}</code>", parse_mode='html')


async def _handle_settings(message: Message, _):
    settings = {
        "基础 URL": _censor_url(db.get(Config.BASE_URL)),
        "聊天模型": db.get(Config.CHAT_MODEL, Config.DEFAULT_CHAT_MODEL),
        "搜索模型": db.get(Config.SEARCH_MODEL, Config.DEFAULT_SEARCH_MODEL),
        "图片生成模型": db.get(Config.IMAGE_MODEL, Config.DEFAULT_IMAGE_MODEL),
        "TTS 模型": db.get(Config.TTS_MODEL, Config.DEFAULT_TTS_MODEL),
        "TTS 语音": db.get(Config.TTS_VOICE, Config.DEFAULT_TTS_VOICE),
        "当前聊天提示": db.get(Config.CHAT_ACTIVE_PROMPT, "默认"),
        "当前搜索提示": db.get(Config.SEARCH_ACTIVE_PROMPT, "默认"),
        "当前 TTS 提示": db.get(Config.TTS_ACTIVE_PROMPT, "默认"),
        "生成 Token 最大数量": f"{db.get(Config.MAX_TOKENS, 0) if db.get(Config.MAX_TOKENS, 0) > 0 else '无限制'}",
        "上下文已启用": db.get(Config.CONTEXT_ENABLED, False),
        "Telegraph 已启用": db.get(Config.TELEGRAPH_ENABLED, False),
        "Telegraph 限制": f"{db.get(Config.TELEGRAPH_LIMIT, 0) if db.get(Config.TELEGRAPH_LIMIT, 0) > 0 else '无限制'}",
        "折叠引用": db.get(Config.COLLAPSIBLE_QUOTE_ENABLED, False),
    }
    settings_text = "<b>Gemini 设置:</b>\n\n" + "\n".join(f"<b>· {k}:</b> <code>{v}</code>" for k, v in settings.items())
    await message.edit(settings_text, parse_mode='html')


async def _handle_max_tokens(message: Message, args: str):
    if not args:
        await _send_usage(message, "max_tokens", "[number] (0 for unlimited)")
        return
    try:
        tokens = int(args)
        if tokens < 0:
            await _show_error(message, "最大 token 数必须为非负整数。")
        else:
            db[Config.MAX_TOKENS] = tokens
            await message.edit(f"<b>最大输出 token 限制已{'清除 (无限制)' if tokens == 0 else f'设置为 {tokens}'}。</b>", parse_mode='html')
    except ValueError:
        await _show_error(message, "无效的 token 数。")


async def _model_set(message: Message, args: str):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _send_usage(message, "model set", "[chat|search|image|tts] [model_name]")
        return
    model_type, model_name = parts
    model_map = {
        "chat": (Config.CHAT_MODEL, None, "聊天"),
        "search": (Config.SEARCH_MODEL, Config.SEARCH_MODELS, "搜索"),
        "image": (Config.IMAGE_MODEL, Config.IMAGE_MODELS, "图片"),
        "tts": (Config.TTS_MODEL, Config.TTS_MODELS, "TTS"),
    }
    if model_type not in model_map:
        await _send_usage(message, "model set", "[chat|search|image|tts] [model_name]")
        return
    key, valid_models, type_name = model_map[model_type]
    if valid_models and model_name not in valid_models:
        await _show_error(message, f"无效的{type_name}模型。请从以下选项中选择: <code>{', '.join(valid_models)}</code>")
        return
    db[key] = model_name
    await message.edit(f"<b>Gemini {type_name}模型已设置为:</b> <code>{model_name}</code>", parse_mode='html')


async def _model_list(message: Message, _):
    client = await _get_gemini_client(message)
    if not client:
        return
    await message.edit("🔍 正在搜索可用模型...", parse_mode='html')
    try:
        all_models = [m.name.replace("models/", "") for m in client.models.list()]
        text = (
            f"<b>可用图片模型:</b>\n<code>{', '.join(Config.IMAGE_MODELS)}</code>\n\n"
            f"<b>可用搜索模型:</b>\n<code>{', '.join(Config.SEARCH_MODELS)}</code>\n\n"
            f"<b>可用 TTS 模型:</b>\n<code>{', '.join(Config.TTS_MODELS)}</code>\n\n"
            f"<b>所有可用模型:</b>\n<code>{', '.join(all_models)}</code>"
        )
        await message.edit(text, parse_mode='html')
    except Exception as e:
        await _show_error(message, f"获取模型时出错:\n<pre><code>{html.escape(str(e))}</code></pre>")


async def _handle_model(message: Message, args: str):
    parts = args.split(maxsplit=1)
    action = parts[0] if parts else None
    action_args = parts[1] if len(parts) > 1 else ""
    actions = {"set": _model_set, "list": _model_list}
    if action in actions:
        await actions[action](message, action_args)
    else:
        await _send_usage(message, "model", "[set|list]")


async def _handle_tts_voice(message: Message, args: str):
    if not args:
        await _send_usage(message, "tts_voice", "[voice_name]")
        return
    db[Config.TTS_VOICE] = args
    await message.edit(f"<b>Gemini TTS 语音已设置为:</b> <code>{args}</code>", parse_mode='html')


async def _prompt_add(message: Message, args: str, prompts: dict):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _send_usage(message, "prompt add", "[name] [prompt]")
        return
    name, text = parts
    prompts[name] = text
    db[Config.PROMPTS] = prompts
    await message.edit(f"<b>系统提示 '{name}' 已添加。</b>", parse_mode='html')


async def _prompt_del(message: Message, name: str, prompts: dict):
    if not name:
        await _send_usage(message, "prompt del", "[name]")
        return
    if name in prompts:
        del prompts[name]
        db[Config.PROMPTS] = prompts
        await message.edit(f"<b>系统提示 '{name}' 已删除。</b>", parse_mode='html')
    else:
        await _show_error(message, f"未找到系统提示 '{name}'。")


async def _prompt_list(message: Message, _, prompts: dict):
    if not prompts:
        await message.edit("<b>未保存任何系统提示。</b>", parse_mode='html')
        return
    text = "<b>可用的系统提示:</b>\n\n" + "\n".join(
        f"• <code>{name}</code>:\n<pre><code>{html.escape(content)}</code></pre>" for name, content in prompts.items())
    await message.edit(text, parse_mode='html')


async def _prompt_set(message: Message, args: str, prompts: dict):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _send_usage(message, "prompt set", "[chat|search|tts] [name]")
        return
    prompt_type, name = parts
    if name not in prompts:
        await _show_error(message, f"未找到系统提示 '{name}'。")
        return
    type_map = {"chat": (Config.CHAT_ACTIVE_PROMPT, "聊天"), "search": (Config.SEARCH_ACTIVE_PROMPT, "搜索"),
                "tts": (Config.TTS_ACTIVE_PROMPT, "TTS")}
    if prompt_type not in type_map:
        await _send_usage(message, "prompt set", "[chat|search|tts] [name]")
        return
    key, type_name = type_map[prompt_type]
    db[key] = name
    await message.edit(f"<b>当前{type_name}系统提示已设置为:</b> <code>{name}</code>", parse_mode='html')


async def _handle_prompt(message: Message, args: str):
    parts = args.split(maxsplit=1)
    action = parts[0] if parts else None
    action_args = parts[1] if len(parts) > 1 else ""
    prompts = db.get(Config.PROMPTS, {})
    actions = {"add": _prompt_add, "del": _prompt_del, "list": _prompt_list, "set": _prompt_set}
    if action in actions:
        await actions[action](message, action_args, prompts)
    else:
        await _send_usage(message, "prompt", "[add|del|list|set]")


async def _context_toggle(message: Message, args: str):
    is_on = args == "on"
    db[Config.CONTEXT_ENABLED] = is_on
    await message.edit(f"<b>对话上下文已{'启用' if is_on else '禁用'}。</b>", parse_mode='html')


async def _context_clear(message: Message, _):
    db[Config.CHAT_HISTORY] = []
    await message.edit("<b>对话历史已清除。</b>", parse_mode='html')


async def _context_show(message: Message, _):
    history = db.get(Config.CHAT_HISTORY, [])
    if not history:
        await message.edit("<b>对话历史为空。</b>", parse_mode='html')
        return
    text = "<b>对话历史:</b>\n\n" + "\n".join(
        f"<b>{'用户' if i % 2 == 0 else '模型'}:</b>\n<pre><code>{html.escape(str(item))}</code></pre>"
        for i, item in enumerate(history))
    try:
        await message.edit(text, parse_mode='html')
    except MessageTooLongError:
        await _show_error(message, "历史记录太长，无法显示。")


async def _handle_context(message: Message, args: str):
    actions = {"on": _context_toggle, "off": _context_toggle, "clear": _context_clear, "show": _context_show}
    if args in actions:
        await actions[args](message, args)
    else:
        await _send_usage(message, "context", "[on|off|clear|show]")


async def _send_to_telegraph(title: str, content: str) -> tuple[str | None, str | None]:
    """Creates a Telegraph page and returns its URL and a potential error message."""
    try:
        if len(content.encode('utf-8')) > 64 * 1024:
            return None, "内容超过 Telegraph 64KB 大小限制"
        client = _get_telegraph_client()
        page = client.create_page(title=title, html_content=content)
        posts = db.get(Config.TELEGRAPH_POSTS, {})
        post_id = str(max(map(int, posts.keys()), default=0) + 1)
        posts[post_id] = {"path": page['path'], "title": title}
        db[Config.TELEGRAPH_POSTS] = posts
        return page['url'], None
    except Exception as e:
        return None, str(e)


async def _telegraph_toggle(message: Message, args: str):
    is_on = args == "on"
    db[Config.TELEGRAPH_ENABLED] = is_on
    await message.edit(f"<b>Telegraph 集成已{'启用' if is_on else '禁用'}。</b>", parse_mode='html')


async def _telegraph_limit(message: Message, args: str):
    if not args:
        await _send_usage(message, "telegraph limit", "[number]")
        return
    try:
        limit = int(args)
        if limit < 0:
            await _show_error(message, "限制必须为非负整数。")
        else:
            db[Config.TELEGRAPH_LIMIT] = limit
            await message.edit(f"<b>Telegraph 字符限制已设置为 {limit}。</b>", parse_mode='html')
    except ValueError:
        await _show_error(message, "无效的限制数。")


async def _telegraph_list(message: Message, args: str):
    posts = db.get(Config.TELEGRAPH_POSTS, {})
    if not posts:
        await message.edit("<b>尚未创建 Telegraph 文章。</b>", parse_mode='html')
        return
    sorted_posts = sorted(posts.items(), key=lambda item: int(item[0]), reverse=True)
    try:
        page = int(args.strip()) if args.strip() else 1
    except ValueError:
        page = 1
    page_size = 30
    total_pages = (len(sorted_posts) + page_size - 1) // page_size or 1
    if not 1 <= page <= total_pages:
        await _show_error(message, f"无效的页码。页码必须在 1 到 {total_pages} 之间。")
        return
    paginated_posts = sorted_posts[(page - 1) * page_size:page * page_size]
    text = f"<b>已创建的 Telegraph 文章 (第 {page}/{total_pages} 页):</b>\n\n" + "\n".join(
        f"• <code>{post_id}</code>: <a href='https://telegra.ph/{data['path']}'>{html.escape(data['title'])}</a>"
        for post_id, data in paginated_posts)
    if total_pages > 1:
        text += f"\n\n使用 <code>,{alias_command('gemini')} telegraph list [page]</code> 查看其他页面。"
    await message.edit(text, parse_mode='html', link_preview=False)


async def _telegraph_del_all(message: Message):
    await message.edit("🗑️ 正在删除所有 Telegraph 文章并创建新身份...", parse_mode='html')
    posts = db.get(Config.TELEGRAPH_POSTS, {})
    if not posts:
        db[Config.TELEGRAPH_TOKEN] = None
        _get_telegraph_client()
        await message.edit("<b>没有可删除的 Telegraph 文章。已创建新的 Telegraph 身份。</b>", parse_mode='html')
        return
    client = _get_telegraph_client()
    errors = sum(1 for post in posts.values() if not _try_delete_telegraph_page(client, post['path']))
    db[Config.TELEGRAPH_POSTS] = {}
    db[Config.TELEGRAPH_TOKEN] = None
    _get_telegraph_client()
    msg = "<b>列表中的所有 Telegraph 文章均已清除。已创建新的 Telegraph 身份。</b>"
    if errors > 0:
        msg += f"\n({errors} 篇文章无法从 telegra.ph 删除)"
    await message.edit(msg, parse_mode='html')


def _try_delete_telegraph_page(client: Telegraph, path: str) -> bool:
    try:
        client.edit_page(path=path, title="[已删除]", html_content="<p>本文已被删除。</p>")
        return True
    except Exception:
        return False


async def _telegraph_del(message: Message, args: str):
    if args == "all":
        await _telegraph_del_all(message)
        return
    id_to_delete = args
    reply = await message.get_reply_message()
    if not id_to_delete and reply and reply.text:
        if match := re.search(r'https://telegra\.ph/([\w/-]+)', reply.text):
            path_to_delete = match.group(1)
            posts = db.get(Config.TELEGRAPH_POSTS, {})
            id_to_delete = next((pid for pid, data in posts.items() if data['path'] == path_to_delete), None)
            if not id_to_delete:
                await _show_error(message, "在数据库中找不到此 Telegraph 文章。")
                return
    if not id_to_delete:
        await _send_usage(message, "telegraph del", "[id|all]")
        return
    posts = db.get(Config.TELEGRAPH_POSTS, {})
    if id_to_delete in posts:
        if _try_delete_telegraph_page(_get_telegraph_client(), posts[id_to_delete]['path']):
            del posts[id_to_delete]
            db[Config.TELEGRAPH_POSTS] = posts
            await message.edit(f"<b>Telegraph 文章 <code>{id_to_delete}</code> 已删除。</b>", parse_mode='html')
        else:
            await _show_error(message, "无法从 Telegraph 删除文章。")
    else:
        await _show_error(message, f"未找到 ID 为 <code>{id_to_delete}</code> 的 Telegraph 文章。")


async def _telegraph_clear(message: Message, _):
    db[Config.TELEGRAPH_POSTS] = {}
    await message.edit("<b>列表中的所有 Telegraph 文章均已清除。</b>", parse_mode='html')


async def _handle_telegraph(message: Message, args: str):
    parts = args.split(maxsplit=1)
    action = parts[0] if parts else None
    action_args = parts[1] if len(parts) > 1 else ""
    actions = {"on": _telegraph_toggle, "off": _telegraph_toggle, "limit": _telegraph_limit,
               "list": _telegraph_list, "del": _telegraph_del, "clear": _telegraph_clear}
    if action in actions:
        await actions[action](message, action_args)
    else:
        await _send_usage(message, "telegraph", "[on|off|limit|list|del|clear]")


async def _handle_collapse(message: Message, args: str):
    if args in ["on", "off"]:
        is_on = args == "on"
        db[Config.COLLAPSIBLE_QUOTE_ENABLED] = is_on
        await message.edit(f"<b>折叠引用已{'启用' if is_on else '禁用'}。</b>", parse_mode='html')
    else:
        await _send_usage(message, "collapse", "[on|off]")


def _build_response_message(prompt_text: str, html_output: str, powered_by: str) -> tuple[str, list]:
    """Builds the final response text and entities."""
    final_text, entities = "", []
    collapsible = db.get(Config.COLLAPSIBLE_QUOTE_ENABLED, False)
    response_text_formatted, response_entities = tg_html.parse(html_output)

    if prompt_text:
        prompt_header = "👤提示:\n"
        entities.append(MessageEntityBold(offset=_get_utf16_length(final_text), length=_get_utf16_length(prompt_header.strip())))
        final_text += prompt_header
        entities.append(MessageEntityBlockquote(offset=_get_utf16_length(final_text), length=_get_utf16_length(prompt_text), collapsed=collapsible))
        final_text += prompt_text + "\n"

    response_header = "🤖回复:\n"
    entities.append(MessageEntityBold(offset=_get_utf16_length(final_text), length=_get_utf16_length(response_header.strip())))
    final_text += response_header
    quote_start = _get_utf16_length(final_text)
    entities.append(MessageEntityBlockquote(offset=quote_start, length=_get_utf16_length(response_text_formatted), collapsed=collapsible))
    final_text += response_text_formatted + "\n"
    for entity in response_entities:
        entity.offset += quote_start
    entities.extend(response_entities)

    entities.append(MessageEntityItalic(offset=_get_utf16_length(final_text), length=_get_utf16_length(powered_by)))
    final_text += powered_by
    return final_text, entities


async def _post_to_telegraph_and_reply(message: Message, prompt_text: str, html_output: str, powered_by: str, limit: int):
    """Handles posting long messages to Telegraph."""
    title = (prompt_text[:15] + '...') if prompt_text and len(prompt_text) > 18 else prompt_text or "Gemini 回复"
    sanitized_html = _sanitize_html_for_telegraph(html_output)
    url, error = await _send_to_telegraph(title, sanitized_html)
    if url:
        reason = f"超过 {limit} 字符" if limit > 0 else "超过 Telegram 消息最大字符数"
        telegraph_link_text = f"🤖<b>回复:</b>\n<blockquote><b>回复{reason}，已上传到 Telegraph:</b>\n {url}</blockquote>"
        final_text = f"👤<b>提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>\n{telegraph_link_text}\n<i>{powered_by}</i>" if prompt_text else f"{telegraph_link_text}\n<i>{powered_by}</i>"
        await message.edit(final_text, parse_mode='html', link_preview=True)
    else:
        await _show_error(message, f"上传到 Telegraph 失败: {error}" if error else "上传到 Telegraph 失败。")


async def _send_response(message: Message, prompt_text: str, html_output: str, powered_by: str):
    """Formats and sends the final response, handling Telegraph for long messages."""
    final_text, entities = _build_response_message(prompt_text, html_output, powered_by)
    telegraph_enabled = db.get(Config.TELEGRAPH_ENABLED)
    telegraph_limit = db.get(Config.TELEGRAPH_LIMIT, 0)

    if telegraph_enabled and telegraph_limit > 0 and len(final_text) > telegraph_limit:
        await _post_to_telegraph_and_reply(message, prompt_text, html_output, powered_by, telegraph_limit)
        return

    try:
        # If the message we are about to edit has media, we can't edit it with a long caption.
        # Instead, we send a new reply and edit the "Thinking..." message to "Completed".
        if message.media and not message.web_preview:
            await message.client.send_message(
                message.chat_id,
                final_text,
                reply_to=message.id,  # Reply to the message with media
                formatting_entities=entities,
                link_preview=False
            )
            await message.edit("✅ 文本生成已完成", parse_mode='html')
        else:
            await message.edit(final_text, formatting_entities=entities, link_preview=False)
    except MessageEmptyError:
        await _show_error(message, "模型返回了空的或无效的回复，无法发送。")
    except MessageTooLongError:
        if telegraph_enabled:
            await _post_to_telegraph_and_reply(message, prompt_text, html_output, powered_by, 0)
        else:
            await _show_error(message, "输出过长。启用 Telegraph 集成以链接形式发送。")


async def _execute_gemini_request(message: Message, args: str, use_search: bool):
    """Generic handler for chat and search requests."""
    edit_text = "🔍 正在搜索..." if use_search else "💬 思考中..."
    powered_by = "Powered by Gemini with Google Search" if use_search else "Powered by Gemini"
    await message.edit(edit_text, parse_mode='html')

    contents = await _get_full_content(message, args)
    if contents is None:
        return
    if not contents:
        await _send_usage(message, "search" if use_search else "", "[query] or reply to a message.")
        return

    output_text = await _call_gemini_api(message, contents, use_search=use_search)
    if output_text is None:
        return

    html_output = _format_text_for_telegram(output_text)
    prompt_text = await _get_prompt_text_for_display(message, args)
    await _send_response(message, prompt_text, html_output, powered_by)


async def _handle_search(message: Message, args: str):
    await _execute_gemini_request(message, args, use_search=True)


async def _handle_chat(message: Message, args: str):
    await _execute_gemini_request(message, args, use_search=False)


async def _handle_image(message: Message, args: str):
    """Handles image generation and editing."""
    await message.edit("🎨 正在生成图片...", parse_mode='html')
    contents = await _get_full_content(message, args)
    if contents is None:
        return
    if not contents:
        await _send_usage(message, "image", "[prompt] (reply to an image to edit)")
        return

    text_response, image_response = await _call_gemini_image_api(message, contents)

    if text_response is None and image_response is None:
        # Error already handled by the API call function
        return

    if image_response:
        image_stream = io.BytesIO()
        image_response.save(image_stream, format='PNG')
        image_stream.seek(0)
        image_stream.name = 'gemini.png'

        prompt_text = await _get_prompt_text_for_display(message, args)
        powered_by = "Powered by Gemini Image Generation"

        caption_html = ""
        if prompt_text:
            caption_html += f"<b>👤提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>\n"
        caption_html += f"<i>{powered_by}</i>"

        try:
            await message.client.send_file(
                message.chat_id,
                file=image_stream,
                caption=caption_html,
                parse_mode='html',
                link_preview=False,
                reply_to=message.id
            )
            await message.edit("✅ 图片生成已完成", parse_mode='html')
        except (MessageTooLongError, MessageEmptyError):
            await _show_error(message, "生成的图片标题过长或无效。")
    elif text_response:
        await _show_error(message, f"模型返回了文本而非图片: {text_response}")
    else:
        # This case is now for when the API returns empty parts, but no exception.
        await _show_error(message, "生成图片失败，且未返回任何文本回复。")


async def _generate_and_send_audio(message: Message, text_to_speak: str, caption_text: str | None = None) -> bool | None:
    """Generates audio from text, sends it as a voice note, and cleans up. Returns True on success, False on failure, None on API error."""
    try:
        audio_path, audio_mime_type = await _call_gemini_tts_api(message, text_to_speak)
    except ValueError as e:
        if str(e).startswith("TOKEN_LIMIT_EXCEEDED"):
            raise e
        await _show_error(message, f"处理语音生成时发生意外错误: {e}")
        return False
    if audio_path is None:
        return None  # API error was handled
    if not audio_mime_type:
        return False  # Should not happen if path is not None, but for safety

    opus_path = f"gemini_tts_{message.id}.ogg"
    success = False
    try:
        await message.edit("⚙️ 正在编码为 Opus...", parse_mode='html')
        params = parse_audio_mime_type(audio_mime_type)
        ffmpeg_cmd = (
            f"ffmpeg -f s{params['bits_per_sample']}le -ar {params['rate']} -ac 1 -i {audio_path} "
            f"-y -c:a libopus {opus_path}"
        )
        process = await asyncio.create_subprocess_shell(
            ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode != 0:
            await _show_error(message, f"FFmpeg 编码失败:\n<pre><code>{html.escape(stderr.decode(errors='ignore').strip())}</code></pre>")
            return False

        final_caption = caption_text or "<i>Powered by Gemini TTS</i>"
        try:
            await message.client.send_file(
                message.chat_id, file=opus_path, voice_note=True, reply_to=message.id,
                caption=final_caption, parse_mode='html'
            )
        except MessageTooLongError:
            await message.client.send_file(
                message.chat_id, file=opus_path, voice_note=True, reply_to=message.id,
                caption="<i>Powered by Gemini TTS</i>", parse_mode='html'
            )
            await message.reply("回复文本过长，无法作为语音消息的标题发送。")
        success = True
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(opus_path):
            os.remove(opus_path)
    return success


async def _handle_tts(message: Message, args: str):
    """Handles text-to-speech functionality."""
    await message.edit("🗣️ 正在生成语音...", parse_mode='html')
    prompt_text = await _get_prompt_text_for_display(message, args)
    if not prompt_text:
        await _send_usage(message, "tts", "[text]")
        return

    try:
        result = await _generate_and_send_audio(message, prompt_text)
        if result is True:
            await message.edit("✅ 语音生成已完成", parse_mode='html')
        elif result is False:
            await _show_error(message, "语音生成失败。")
        # if result is None, do nothing as the error is already displayed.
    except ValueError as e:
        if str(e).startswith("TOKEN_LIMIT_EXCEEDED"):
            total_tokens = str(e).split(":")[1].strip()
            await _show_error(message, f"文本超过 1000 tokens 限制 ({total_tokens} tokens)，无法生成语音。")
        else:
            await _show_error(message, f"发生意外错误: {e}")


async def _execute_audio_request(message: Message, args: str, use_search: bool):
    """Generic handler for audio chat and search requests."""
    edit_text = "🔍 正在搜索..." if use_search else "💬 思考中..."
    powered_by = "Powered by Gemini with Google Search" if use_search else "Powered by Gemini"
    await message.edit(edit_text, parse_mode='html')

    contents = await _get_full_content(message, args)
    if contents is None:
        return
    if not contents:
        await _send_usage(message, "search_audio" if use_search else "_audio", "[query] or reply to a message.")
        return

    output_text = await _call_gemini_api(message, contents, use_search=use_search)
    if output_text is None:
        return

    prompt_text = await _get_prompt_text_for_display(message, args)
    caption = ""
    if prompt_text:
        caption = f"<b>👤提示:</b>\n<blockquote>{html.escape(prompt_text)}</blockquote>\n"
    caption += f"<i>{powered_by}</i>"

    fallback_reason = None
    try:
        tts_result = await _generate_and_send_audio(message, output_text, caption_text=caption)
    except ValueError as e:
        if str(e).startswith("TOKEN_LIMIT_EXCEEDED"):
            total_tokens = str(e).split(":")[1].strip()
            fallback_reason = f"文本超过 1000 tokens 限制 ({total_tokens} tokens)。"
            tts_result = False
        else:
            raise e

    if tts_result is True:
        await message.edit("✅ 语音生成已完成", parse_mode='html')
    elif tts_result is False:
        fallback_message = fallback_reason or "语音生成失败。"
        await message.edit(f"{fallback_message} 将以文本形式发送回复。", parse_mode='html')
        html_output = _format_text_for_telegram(output_text)
        prompt_text = await _get_prompt_text_for_display(message, args)
        await _send_response(message, prompt_text, html_output, powered_by)
    # if tts_result is None, do nothing as the error is already displayed.


async def _handle_audio(message: Message, args: str):
    await _execute_audio_request(message, args, use_search=False)


async def _handle_search_audio(message: Message, args: str):
    await _execute_audio_request(message, args, use_search=True)


@listener(
    command="gemini",
    description="""
Google Gemini AI 插件。需要 PagerMaid-Modify 1.5.8 及以上版本。

核心功能:
- `gemini [query]`: 与模型聊天 (默认)。
- `gemini _audio [query]`: 获取模型回复并转换为语音。
- `gemini search [query]`: 使用 Gemini AI 支持的 Google 搜索。
- `gemini search_audio [query]`: 获取搜索结果并转换为语音。
- `gemini tts [text]`: 将文本转换为语音。需要安装 ffmpeg。
- `gemini image [prompt]`: 生成或编辑图片。

设置:
- `gemini settings`: 显示当前配置。
- `gemini set_api_key [key]`: 设置您的 Gemini API 密钥。
- `gemini set_base_url [url]`: 设置自定义 Gemini API 基础 URL。留空以清除。
- `gemini max_tokens [number]`: 设置最大输出 token 数 (0 表示无限制)。
- `gemini tts_voice [name]`: 设置 TTS 语音。尝试不同语音: https://aistudio.google.com/generate-speech
- `gemini collapse [on|off]`: 开启或关闭折叠引用。

模型管理:
- `gemini model list`: 列出可用模型。
- `gemini model set [chat|search|image|tts] [name]`: 设置聊天、搜索、图片或 TTS 模型。

提示词管理:
- `gemini prompt list`: 列出所有已保存的系统提示。
- `gemini prompt add [name] [prompt]`: 添加一个新的系统提示。
- `gemini prompt del [name]`: 删除一个系统提示。
- `gemini prompt set [chat|search|tts] [name]`: 设置聊天、搜索或 TTS 的激活系统提示。

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
    """Main handler for the gemini plugin, dispatching to sub-handlers."""
    parts = message.arguments.split(maxsplit=1)
    sub_command = parts[0] if parts else None
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "set_api_key": _handle_set_api_key, "set_base_url": _handle_set_base_url,
        "settings": _handle_settings, "max_tokens": _handle_max_tokens,
        "model": _handle_model, "tts_voice": _handle_tts_voice,
        "prompt": _handle_prompt, "search": _handle_search,
        "tts": _handle_tts, "image": _handle_image,
        "context": _handle_context, "telegraph": _handle_telegraph,
        "collapse": _handle_collapse, "_audio": _handle_audio,
        "search_audio": _handle_search_audio,
    }

    try:
        if sub_command in handlers:
            await handlers[sub_command](message, args)
        else:
            await _handle_chat(message, message.arguments)
    except Exception:
        await message.edit(f"发生意外错误:\n<pre><code>{html.escape(traceback.format_exc())}</code></pre>", parse_mode='html')
