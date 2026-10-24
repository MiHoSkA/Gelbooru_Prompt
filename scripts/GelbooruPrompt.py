import asyncio
import io
import json
import os
import re
import tempfile
import threading
import warnings
from urllib.parse import parse_qs, urlsplit

import aiohttp
from PIL import Image, ImageOps
import numpy as np
import gradio as gr
from modules import scripts, shared, script_callbacks
from scripts.Gel import Gelbooru, GelbooruException, GelbooruNotFoundException, get_proxy

LOCALE = {'ru': {'title': 'Gelbooru',
        'accordion_random': 'Случайный пост',
        'accordion_load': 'Загрузить пост по ссылке или ID',
        'label_include': 'Включить теги',
        'label_exclude': 'Исключить теги',
        'label_tags': 'Теги',
        'label_url': 'Ссылка на пост',
        'label_post_input': 'Ссылка на пост или ID',
        'label_status': 'Статус',
        'button_random': 'Случайный',
        'button_clear': 'Очистить',
        'button_load': 'Загрузить пост',
        'button_clear_manual': 'Очистить',
        'error_auth': 'Необходимо войти в аккаунт Gelbooru (укажите API ключ и ID пользователя в настройках)',
        'error_no_post': 'Не удалось найти пост с указанными тегами',
        'error_timeout': 'Превышен таймаут соединения с Gelbooru. Попробуйте позже или проверьте интернет.',
        'error_525': 'Сайт Gelbooru временно недоступен (ошибка 525). Попробуйте позже.',
        'error_gelbooru': 'Ошибка при обращении к Gelbooru: ',
        'error_unexpected': 'Непредвиденная ошибка: ',
        'error_no_new': 'Все доступные посты с такими тегами уже были показаны. Попробуйте другие теги.',
        'error_post_not_found': 'Пост не найден',
        'error_invalid_id': 'Не удалось распознать ID поста. Укажите ссылку вида '
                            'https://gelbooru.com/index.php?page=post&s=view&id=123456 или просто число',
        'error_post_not_found_id': 'Пост с ID {id} не найден',
        'error_gelbooru_blocked': 'Не возможно получить доступ к gelbooru.com, если вы из России, вам нужно включить '
                                  'желательно VPN ! Так как данная платформа не доступна на территории российской '
                                  'федерации! Если вы не из России и видите это сообщение то это означает что данная '
                                  'платформа не доступна и в вашей стране и вам тоже нужно включить VPN! Если не '
                                  'помогает VPN, это означает что на данный момент проблемы на стороне самого сервиса '
                                  'Gelbooru !',
        'error_video_preview': 'У этого видео нет подходящего статичного превью; теги и ссылка на пост получены.',
        'success': 'Успешно',
        'placeholder_include': 'например: 1girl, blue_hair, solo',
        'placeholder_exclude': 'например: nsfw, text, watermark',
        'placeholder_post_input': 'https://gelbooru.com/index.php?page=post&s=view&id=123456 или просто 123456',
        'setting_api_key_label': 'API ключ',
        'setting_api_key_info': '<a href="https://gelbooru.com/index.php?page=account&s=options" '
                                'target="_blank">Настройки аккаунта</a>',
        'setting_user_id_label': 'ID пользователя',
        'setting_user_id_info': '<a href="https://gelbooru.com/index.php?page=account&s=options" '
                                'target="_blank">Настройки аккаунта</a>',
        'setting_replace_underscores_label': 'Заменять подчёркивания на пробелы в полученных тегах',
        'setting_exclusion_list_label': 'Список исключений для замены подчёркиваний',
        'setting_exclusion_list_info': 'Укажите теги, в которых не нужно заменять подчёркивания на пробелы, через '
                                       'запятую.',
        'setting_ignore_tags_label': 'Игнорируемые теги (не показывать)',
        'setting_ignore_tags_info': 'Укажите теги, которые будут удалены из результата (не влияют на поиск). Через '
                                    'запятую, можно с пробелами или подчёркиваниями.',
        'setting_language_label': 'Язык интерфейса',
        'setting_proxy_enabled_label': 'Включить прокси',
        'setting_proxy_url_label': 'URL прокси (например, http://user:pass@host:port)',
        'error_preview': 'Превью недоступно; теги и ссылка на пост получены.',
        'error_proxy': 'Проверьте настройки включённого HTTP/HTTPS прокси.',
        'warning_history': 'Не удалось сохранить историю просмотренных постов на диск.',
        'setting_universal_blacklist_label': 'Универсальный чёрный список',
        'setting_universal_blacklist_info': 'Теги через запятую: исключаются из поиска и удаляются из всех '
                                            'результатов.',
        'setting_display_all_content_label': 'Показывать весь контент',
        'setting_display_all_content_info': 'По умолчанию выключено. Запрашивает контент, скрытый фильтрами аккаунта '
                                            'Gelbooru.',
        'setting_language_info': 'После применения настроек перезагрузите интерфейс, чтобы обновить все подписи.'},
 'en': {'title': 'Gelbooru',
        'accordion_random': 'Random Post',
        'accordion_load': 'Load Post by URL or ID',
        'label_include': 'Include tags',
        'label_exclude': 'Exclude tags',
        'label_tags': 'Tags',
        'label_url': 'Post URL',
        'label_post_input': 'Post URL or ID',
        'label_status': 'Status',
        'button_random': 'Random',
        'button_clear': 'Clear',
        'button_load': 'Load Post',
        'button_clear_manual': 'Clear',
        'error_auth': 'You must log in to Gelbooru (provide API key and user ID in settings)',
        'error_no_post': 'No post found with the specified tags',
        'error_timeout': 'Connection to Gelbooru timed out. Please try again later or check your internet.',
        'error_525': 'Gelbooru is temporarily unavailable (error 525). Please try again later.',
        'error_gelbooru': 'Error while accessing Gelbooru: ',
        'error_unexpected': 'Unexpected error: ',
        'error_no_new': 'All available posts with these tags have already been shown. Try different tags.',
        'error_post_not_found': 'Post not found',
        'error_invalid_id': 'Could not parse post ID. Provide a link like '
                            'https://gelbooru.com/index.php?page=post&s=view&id=123456 or just the number',
        'error_post_not_found_id': 'Post with ID {id} not found',
        'error_gelbooru_blocked': 'Cannot access gelbooru.com. If you are from Russia, please enable VPN, as this '
                                  'platform is blocked in the Russian Federation. If you are not from Russia and see '
                                  'this message, it means the platform is also unavailable in your country, please '
                                  "enable VPN. If VPN does not help, it means there are issues on Gelbooru's side.",
        'error_video_preview': 'This video has no supported still preview; the tags and post URL are ready.',
        'success': 'Success',
        'placeholder_include': 'e.g. 1girl, blue_hair, solo',
        'placeholder_exclude': 'e.g. nsfw, text, watermark',
        'placeholder_post_input': 'https://gelbooru.com/index.php?page=post&s=view&id=123456 or just 123456',
        'setting_api_key_label': 'API key',
        'setting_api_key_info': '<a href="https://gelbooru.com/index.php?page=account&s=options" '
                                'target="_blank">Account settings</a>',
        'setting_user_id_label': 'User ID',
        'setting_user_id_info': '<a href="https://gelbooru.com/index.php?page=account&s=options" '
                                'target="_blank">Account settings</a>',
        'setting_replace_underscores_label': 'Replace underscores with spaces in fetched tags',
        'setting_exclusion_list_label': 'Exclusion list for underscore replacement',
        'setting_exclusion_list_info': 'Specify tags where underscores should NOT be replaced with spaces, separated '
                                       'by commas.',
        'setting_ignore_tags_label': 'Ignored tags (do not show)',
        'setting_ignore_tags_info': 'Specify tags to remove from the result (does not affect search). Separated by '
                                    'commas, with spaces or underscores allowed.',
        'setting_language_label': 'Interface language',
        'setting_proxy_enabled_label': 'Enable proxy',
        'setting_proxy_url_label': 'Proxy URL (e.g., http://user:pass@host:port)',
        'error_preview': 'Preview is unavailable; the tags and post URL are ready.',
        'error_proxy': 'Check the enabled HTTP/HTTPS proxy settings.',
        'warning_history': 'The viewed history could not be saved to disk.',
        'setting_universal_blacklist_label': 'Universal blacklist',
        'setting_universal_blacklist_info': 'Comma-separated tags excluded from searches and removed from all results.',
        'setting_display_all_content_label': 'Display all content',
        'setting_display_all_content_info': 'Disabled by default. Requests content otherwise hidden by Gelbooru '
                                            'account filters.',
        'setting_language_info': 'After applying settings, use Reload UI to update all labels.'}}

LOCALE["en"].update({"error_no_static": "No post with a supported static preview was found in 8 attempts.", "error_rate_limit": "Gelbooru rate limit reached. Please try again later."})
LOCALE["ru"].update({"error_no_static": "За 8 попыток не найден пост с подходящим статичным превью.", "error_rate_limit": "Превышен лимит запросов Gelbooru. Повторите попытку позже."})

SEEN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seen_posts.json")
SEEN_LOCK = threading.RLock()
SESSION_SEEN = set()
ANIMATED_IMAGE = object()
PREVIEW_PENDING = object()
CALLBACK_TIMEOUT = 60
MAX_RANDOM_ATTEMPTS = 8
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 32_000_000
MAX_IMAGE_SIDE = 8192


def _locale():
    language = getattr(shared.opts, "gpr_language", "en")
    return LOCALE.get(language if isinstance(language, str) else "en", LOCALE["en"])


def _tags(value):
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    elif value is None:
        values = []
    else:
        values = [value]
    result = []
    for item in values:
        tag = re.sub(r"\s+", "_", str(item).strip()) if item is not None else ""
        if tag and tag not in result:
            result.append(tag)
    return result


def _post_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,20}", text):
        return None
    number = int(text)
    return number if number > 0 else None


def _parse_post_input(value):
    text = str(value or "").strip()
    post_id = _post_id(text)
    if post_id is not None:
        return post_id
    try:
        url = urlsplit(text)
        if (url.scheme.lower() not in ("http", "https")
                or (url.hostname or "").lower() not in ("gelbooru.com", "www.gelbooru.com")
                or url.username or url.password
                or url.port not in (None, 80, 443)
                or url.path not in ("", "/", "/index.php")):
            return None
        ids = parse_qs(url.query, keep_blank_values=True).get("id", [])
        return _post_id(ids[0]) if len(ids) == 1 else None
    except (TypeError, ValueError):
        return None


def _read_seen_ids():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            return {number for value in data if (number := _post_id(value)) is not None}
    except (OSError, ValueError, TypeError):
        pass
    return set()


def load_seen_ids():
    with SEEN_LOCK:
        return _read_seen_ids() | SESSION_SEEN


def _write_seen_ids(ids):
    temporary = None
    try:
        folder = os.path.dirname(os.path.abspath(SEEN_FILE))
        os.makedirs(folder, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                         prefix=".seen_posts-", suffix=".json", delete=False) as file:
            temporary = file.name
            json.dump(sorted(ids), file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, SEEN_FILE)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_seen_ids(ids):
    with SEEN_LOCK:
        normalized = {number for value in ids if (number := _post_id(value)) is not None}
        merged = _read_seen_ids() | SESSION_SEEN | normalized
        SESSION_SEEN.update(merged)
        return _write_seen_ids(merged)


def _claim_seen(post_id):
    with SEEN_LOCK:
        if post_id in _read_seen_ids() | SESSION_SEEN:
            return False, True
        return True, save_seen_ids({post_id})


def _get_proxy():
    return get_proxy()


def _image_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("//"):
        value = "https:" + value
    try:
        url = urlsplit(value)
        if (url.scheme.lower() not in ("http", "https") or not url.hostname
                or url.username or url.password
                or any(char.isspace() or ord(char) < 32 for char in value)):
            return None
        url.port
    except ValueError:
        return None
    return value


def is_video_url(url):
    if not isinstance(url, str):
        return False
    extensions = (".mp4", ".webm", ".mov", ".avi", ".m4v", ".gifv", ".mpeg", ".mpg", ".m3u8")
    try:
        return urlsplit(url).path.lower().endswith(extensions)
    except ValueError:
        return False


def _decode_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if (image.width < 1 or image.height < 1
                        or image.width > MAX_IMAGE_SIDE or image.height > MAX_IMAGE_SIDE
                        or image.width * image.height > MAX_IMAGE_PIXELS):
                    return None
                if getattr(image, "is_animated", False):
                    return ANIMATED_IMAGE
                image = ImageOps.exif_transpose(image)
                return np.array(image.convert("RGB"), copy=True)
    except Exception:
        return None


async def fetch_image(session, url, timeout=60, retries=2, state=None):
    url = _image_url(url)
    if not url or is_video_url(url):
        return None
    try:
        duration = min(float(timeout), CALLBACK_TIMEOUT)
        attempts = min(max(int(retries), 1), 3)
    except (TypeError, ValueError, OverflowError):
        return None
    if not 0 < duration <= CALLBACK_TIMEOUT:
        return None
    proxy = get_proxy()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration
    for _ in range(attempts):
        remaining = deadline - loop.time()
        if remaining <= 0:
            return None
        try:
            async with session.get(url, headers={"Referer": "https://gelbooru.com/"},
                                   timeout=aiohttp.ClientTimeout(total=remaining), proxy=proxy) as response:
                if response.status != 200:
                    if response.status in (400, 401, 403, 404):
                        return None
                    continue
                size = response.content_length
                if size is not None and size > MAX_IMAGE_BYTES:
                    return None
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    if len(data) + len(chunk) > MAX_IMAGE_BYTES:
                        return None
                    data.extend(chunk)
                remaining = deadline - loop.time()
                if not data or remaining <= 0:
                    return None
                decoded = await asyncio.wait_for(asyncio.to_thread(_decode_image, bytes(data)), min(5, remaining))
                if decoded is ANIMATED_IMAGE:
                    if state is not None:
                        state["animated"] = True
                    return None
                return decoded
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            if deadline - loop.time() <= 0:
                return None
        except Exception:
            return None
    return None


def filter_tags(tags, ignore_list):
    ignored = {tag.casefold() for tag in _tags(ignore_list)}
    return [tag for tag in _tags(tags) if tag.casefold() not in ignored]


def _result_tags(post):
    raw = post.get_tags()
    raw = raw.split() if isinstance(raw, str) else raw
    ignored = _tags(getattr(shared.opts, "gpr_ignore_tags", ""))
    ignored += _tags(getattr(shared.opts, "gpr_universalBlacklist", ""))
    tags = filter_tags(raw, ignored)
    if getattr(shared.opts, "gpr_replaceUnderscores", True):
        exclusions = {tag.casefold() for tag in _tags(getattr(shared.opts, "gpr_undersocreReplacementExclusionList", ""))}
        tags = [tag if tag.casefold() in exclusions else tag.replace("_", " ") for tag in tags]
    return ", ".join(tags)


def _error_status(error, locale):
    if isinstance(error, asyncio.TimeoutError):
        return locale["error_timeout"]
    message = str(error)
    if re.search(r"\b(?:401|403)\b", message):
        return locale["error_auth"]
    if re.search(r"\b429\b", message):
        return locale["error_rate_limit"]
    if re.search(r"\b525\b", message):
        return locale["error_525"]
    if isinstance(error, GelbooruException):
        return locale["error_gelbooru"].rstrip(" :")
    if isinstance(error, aiohttp.ClientError):
        return locale["error_gelbooru"].rstrip(" :")
    return locale["error_unexpected"].rstrip(" :")


async def _preview(post, deadline, state=None):
    candidates = []
    for attribute in ("sample_url", "preview_url", "file_url"):
        candidate = _image_url(getattr(post, attribute, None))
        if candidate and not is_video_url(candidate) and candidate not in candidates:
            candidates.append(candidate)
    async with aiohttp.ClientSession() as session:
        for candidate in candidates:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            preview = await fetch_image(session, candidate, timeout=min(12, remaining), retries=1, state=state)
            if preview is not None:
                return preview
    return None


async def _post_result(post, deadline, state, locale, history_saved=True, preview=PREVIEW_PENDING):
    post_id = _post_id(getattr(post, "id", None))
    if post_id is None:
        return "", None, "", locale["error_no_post"]
    tags = _result_tags(post)
    post_url = f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}"
    state.update(tags=tags, url=post_url)
    if preview is PREVIEW_PENDING:
        preview = await _preview(post, deadline)
    if preview is not None:
        status = locale["success"]
    elif is_video_url(getattr(post, "file_url", None)):
        status = locale["error_video_preview"]
    else:
        status = locale["error_preview"]
    if not history_saved:
        status += " " + locale["warning_history"]
    return tags, preview, post_url, status


async def _request_result(include=None, exclude=None, post_input=None, manual=False):
    locale = _locale()
    key = str(getattr(shared.opts, "gpr_api_key", "") or "").strip()
    user_id = _post_id(getattr(shared.opts, "gpr_user_id", None))
    if not key or user_id is None:
        return "", None, "", locale["error_auth"]
    try:
        get_proxy()
    except Exception:
        return "", None, "", locale["error_proxy"]
    selected_id = _parse_post_input(post_input) if manual else None
    if manual and selected_id is None:
        return "", None, "", locale["error_invalid_id"]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + CALLBACK_TIMEOUT
    state = {}

    async def request():
        client = Gelbooru(api_key=key, user_id=str(user_id), timeout=CALLBACK_TIMEOUT,
                          display_all_content=getattr(shared.opts, "gpr_displayAllContent", False) is True)
        if manual:
            post = await client.get_post(selected_id)
            if post is None:
                return "", None, "", locale["error_post_not_found_id"].format(id=selected_id)
            return await _post_result(post, deadline, state, locale)
        included = _tags(include)
        excluded = _tags(exclude) + _tags(getattr(shared.opts, "gpr_universalBlacklist", ""))
        excluded = list(dict.fromkeys(excluded))
        unusable = 0
        for _ in range(MAX_RANDOM_ATTEMPTS):
            post = await client.random_post(tags=included or None, exclude_tags=excluded or None)
            if post is None:
                return "", None, "", locale["error_no_post"]
            post_id = _post_id(getattr(post, "id", None))
            if post_id is None or post_id in await asyncio.to_thread(load_seen_ids):
                continue
            video = is_video_url(getattr(post, "file_url", None))
            still_candidates = [candidate for attribute in ("sample_url", "preview_url")
                                if (candidate := _image_url(getattr(post, attribute, None))) and not is_video_url(candidate)]
            if video and not still_candidates:
                unusable += 1
                continue
            preview_state = {}
            if not video:
                state.update(tags=_result_tags(post), url=f"https://gelbooru.com/index.php?page=post&s=view&id={post_id}")
            preview = await _preview(post, deadline, preview_state)
            if preview is None and (video or preview_state.get("animated")):
                state.clear()
                unusable += 1
                continue
            claimed, saved = await asyncio.to_thread(_claim_seen, post_id)
            if claimed:
                return await _post_result(post, deadline, state, locale, saved, preview)
            state.clear()
        return "", None, "", locale["error_no_static"] if unusable else locale["error_no_new"]

    try:
        return await asyncio.wait_for(request(), timeout=CALLBACK_TIMEOUT)
    except GelbooruNotFoundException:
        return "", None, "", locale["error_post_not_found_id"].format(id=selected_id) if manual else locale["error_no_post"]
    except Exception as error:
        if state.get("url"):
            return state["tags"], None, state["url"], locale["error_preview"]
        return "", None, "", _error_status(error, locale)


async def get_random_tags_with_status(include, exclude):
    return await _request_result(include=include, exclude=exclude)


async def get_random_tags(include, exclude):
    tags, preview, post_url, status = await get_random_tags_with_status(include, exclude)
    return tags if post_url else status, preview, post_url or _locale()["error_post_not_found"]


async def get_post_by_url(post_input):
    return await _request_result(post_input=post_input, manual=True)


class GPRScript(scripts.Script):
    def title(self):
        return "Gelbooru Prompt"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        locale = _locale()
        with gr.Accordion(locale["title"], open=False):
            with gr.Accordion(locale["accordion_random"], open=True):
                include_tags_textbox = gr.Textbox(label=locale["label_include"], placeholder=locale["placeholder_include"])
                exclude_tags_textbox = gr.Textbox(label=locale["label_exclude"], placeholder=locale["placeholder_exclude"])
                with gr.Row():
                    random_button = gr.Button(value=locale["button_random"], variant="primary", size="sm")
                    clear_button = gr.Button(value=locale["button_clear"], size="sm")
                result_tags_textbox = gr.Textbox(label=locale["label_tags"], show_copy_button=True, interactive=False)
                preview_image = gr.Image(interactive=False, show_label=False, height=400)
                url_textbox = gr.Textbox(label=locale["label_url"], show_copy_button=True, interactive=False)
                status_textbox = gr.Textbox(label=locale["label_status"], interactive=False)
            with gr.Accordion(locale["accordion_load"], open=False):
                post_input_textbox = gr.Textbox(label=locale["label_post_input"], placeholder=locale["placeholder_post_input"])
                with gr.Row():
                    load_post_button = gr.Button(value=locale["button_load"], variant="secondary", size="sm")
                    clear_manual_button = gr.Button(value=locale["button_clear_manual"], size="sm")
                manual_tags_textbox = gr.Textbox(label=locale["label_tags"], show_copy_button=True, interactive=False)
                manual_preview_image = gr.Image(interactive=False, show_label=False, height=400)
                manual_url_textbox = gr.Textbox(label=locale["label_url"], show_copy_button=True, interactive=False)
                manual_status_textbox = gr.Textbox(label=locale["label_status"], interactive=False)
        random_button.click(fn=get_random_tags_with_status, inputs=[include_tags_textbox, exclude_tags_textbox],
                            outputs=[result_tags_textbox, preview_image, url_textbox, status_textbox])
        clear_button.click(fn=lambda: ("", None, "", ""), inputs=[],
                           outputs=[result_tags_textbox, preview_image, url_textbox, status_textbox])
        load_post_button.click(fn=get_post_by_url, inputs=[post_input_textbox],
                               outputs=[manual_tags_textbox, manual_preview_image, manual_url_textbox, manual_status_textbox])
        clear_manual_button.click(fn=lambda: ("", None, "", ""), inputs=[],
                                  outputs=[manual_tags_textbox, manual_preview_image, manual_url_textbox, manual_status_textbox])
        return []

    def on_ui_settings():
        locale = _locale()
        section = ("gpr", "Gelbooru Prompt")
        options = {
            "gpr_api_key": shared.OptionInfo("", locale["setting_api_key_label"], gr.Textbox,
                                               component_args={"type": "password"}, restrict_api=True).info(locale["setting_api_key_info"]),
            "gpr_user_id": shared.OptionInfo("", locale["setting_user_id_label"], gr.Textbox).info(locale["setting_user_id_info"]),
            "gpr_replaceUnderscores": shared.OptionInfo(True, locale["setting_replace_underscores_label"]),
            "gpr_undersocreReplacementExclusionList": shared.OptionInfo(
                "0_0,(o)_(o),+_+,+_-,._.,<o>_<o>,<|>_<|>,=_=,>_<,3_3,6_9,>_o,@_@,^_^,o_o,u_u,x_x,|_|,||_||",
                locale["setting_exclusion_list_label"]).info(locale["setting_exclusion_list_info"]),
            "gpr_ignore_tags": shared.OptionInfo("", locale["setting_ignore_tags_label"], gr.Textbox).info(locale["setting_ignore_tags_info"]),
            "gpr_universalBlacklist": shared.OptionInfo("", locale["setting_universal_blacklist_label"], gr.Textbox).info(locale["setting_universal_blacklist_info"]),
            "gpr_displayAllContent": shared.OptionInfo(False, locale["setting_display_all_content_label"]).info(locale["setting_display_all_content_info"]),
            "gpr_language": shared.OptionInfo("en", locale["setting_language_label"], gr.Radio, component_args={"choices": ["ru", "en"]}).info(locale["setting_language_info"]),
            "gpr_proxy_enabled": shared.OptionInfo(False, locale["setting_proxy_enabled_label"]),
            "gpr_proxy_url": shared.OptionInfo("", locale["setting_proxy_url_label"], gr.Textbox,
                                                 component_args={"type": "password"}, restrict_api=True),
        }
        for key, option in options.items():
            option.section = section
            shared.opts.add_option(key, option)

    script_callbacks.on_ui_settings(on_ui_settings)
