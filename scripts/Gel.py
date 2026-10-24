import asyncio
import json
import math
import os
import reprlib
from datetime import datetime
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse
from xml.parsers.expat import ExpatError

import aiohttp
import xmltodict
from furl import furl

from modules import shared


class GelbooruException(Exception):
    pass


class GelbooruNotFoundException(GelbooruException):
    pass


def _integer(value, default=0):
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError, OverflowError):
        return default


def _boolean(value):
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    return value is True or value == 1


def _positive_integer(value, field, minimum=1, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise GelbooruException(f"Invalid {field}.")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise GelbooruException(f"Invalid {field}.") from None
    if result < minimum or (maximum is not None and result > maximum):
        raise GelbooruException(f"Invalid {field}.")
    return result


def _media_url(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if value.startswith('//'):
        value = 'https:' + value
    try:
        parsed = urlparse(value)
        valid = (
            parsed.scheme.lower() in ('http', 'https') and parsed.hostname
            and not parsed.username and not parsed.password
            and not any(char.isspace() or ord(char) < 32 for char in value)
        )
        parsed.port
    except ValueError:
        return ''
    return value if valid else ''


def get_proxy():
    if not getattr(shared.opts, 'gpr_proxy_enabled', False):
        return None
    proxy_url = getattr(shared.opts, 'gpr_proxy_url', '')
    if not isinstance(proxy_url, str) or not proxy_url.strip():
        raise GelbooruException("Proxy is enabled, but its HTTP/HTTPS URL is missing.")
    proxy_url = proxy_url.strip()
    try:
        parsed = urlparse(proxy_url)
        valid = (
            parsed.scheme.lower() in ('http', 'https') and parsed.hostname
            and not parsed.query and not parsed.fragment and parsed.path in ('', '/')
            and not any(char.isspace() or ord(char) < 32 for char in proxy_url)
        )
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise GelbooruException("Invalid proxy URL. Use an HTTP/HTTPS proxy.")
    return proxy_url


class GelbooruImage:
    def __init__(self, payload: dict, gelbooru):
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise GelbooruException("Gelbooru returned an invalid post.")
        payload = {key.lstrip('@'): value for key, value in payload.items()}
        self._gelbooru = gelbooru
        self.id = _positive_integer(payload.get('id'), 'post ID')
        self.creator_id = _integer(payload.get('creator_id')) or None
        self.created_at = _datetime(payload.get('created_at'))
        self.file_url = _media_url(payload.get('file_url'))
        self.sample_url = _media_url(payload.get('sample_url'))
        self.preview_url = _media_url(payload.get('preview_url'))
        self.filename = os.path.basename(urlparse(self.file_url).path)
        self.source = payload.get('source') or None
        self.hash = payload.get('md5')
        self.height = max(0, _integer(payload.get('height')))
        self.width = max(0, _integer(payload.get('width')))
        self.rating = payload.get('rating')
        self.has_sample = _boolean(payload.get('has_sample'))
        self.has_comments = _boolean(payload.get('has_comments'))
        self.has_notes = _boolean(payload.get('has_notes'))
        self.has_children = _boolean(payload.get('has_children'))
        tags = payload.get('tags')
        if isinstance(tags, str):
            self.tags = tags.split()
        elif isinstance(tags, list):
            self.tags = [tag for tag in tags if isinstance(tag, str) and tag]
        else:
            self.tags = []
        try:
            self.change = datetime.fromtimestamp(_integer(payload.get('change')))
        except (ValueError, OverflowError, OSError):
            self.change = None
        self.directory = payload.get('directory')
        self.status = payload.get('status')
        self.locked = _boolean(payload.get('post_locked'))
        self.score = _integer(payload.get('score'))
        self._payload = payload

    def __str__(self):
        return f"https://gelbooru.com/index.php?page=post&s=view&id={self.id}"

    def __int__(self):
        return self.id

    def __repr__(self):
        rep = reprlib.Repr()
        return f"<GelbooruImage(id={self.id}, filename={rep.repr(self.filename)}, owner={rep.repr(self.creator_id)})>"

    def get_tags(self):
        return self.tags


API_GELBOORU = 'https://gelbooru.com/'


class Gelbooru:
    SORT_COUNT = 'count'
    SORT_DATE = 'date'
    SORT_NAME = 'name'
    SORT_ASC = 'ASC'
    SORT_DESC = 'DESC'
    MAX_LIMIT = 100
    MAX_RESPONSE_BYTES = 8 * 1024 * 1024

    def __init__(self, api_key: Optional[str] = None,
                 user_id: Optional[str] = None,
                 loop: Optional[asyncio.AbstractEventLoop] = None,
                 api: Optional[str] = API_GELBOORU,
                 timeout: int = 60,
                 display_all_content: bool = False):
        try:
            timeout = float(timeout)
        except (TypeError, ValueError, OverflowError):
            raise GelbooruException("Invalid request timeout.") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise GelbooruException("Invalid request timeout.")
        self._api_key = api_key
        self._user_id = user_id
        self._loop = loop
        self._base_url = api or API_GELBOORU
        self._timeout = aiohttp.ClientTimeout(total=min(timeout, 60))
        self._display_all_content = display_all_content is True

    def _get_proxy_settings(self):
        return get_proxy()

    @staticmethod
    def _parse_posts(payload):
        try:
            stripped = payload.lstrip()
            is_json = (
                stripped.startswith((b'{', b'[')) if isinstance(stripped, bytes)
                else isinstance(stripped, str) and stripped.startswith(('{', '['))
            )
            parsed = json.loads(payload) if is_json else xmltodict.parse(payload, disable_entities=True)
        except (ValueError, TypeError, AttributeError, ExpatError):
            raise GelbooruException("Gelbooru returned a malformed response.") from None
        if isinstance(parsed, list):
            posts, count = parsed, None
        elif isinstance(parsed, dict):
            if 'posts' in parsed:
                container = parsed['posts']
                if container is None:
                    return [], 0
            elif 'post' in parsed or '@attributes' in parsed:
                container = parsed
            else:
                raise GelbooruException("Gelbooru returned an invalid API response.")
            if not isinstance(container, dict):
                raise GelbooruException("Gelbooru returned an invalid API response.")
            attributes = container.get('@attributes') or {}
            if not isinstance(attributes, dict):
                raise GelbooruException("Gelbooru returned an invalid post count.")
            count = container.get('@count', container.get('count', attributes.get('count')))
            posts = container.get('post') or []
            if isinstance(posts, dict):
                posts = [posts]
        else:
            raise GelbooruException("Gelbooru returned an invalid API response.")
        if not isinstance(posts, list) or any(not isinstance(post, dict) for post in posts):
            raise GelbooruException("Gelbooru returned invalid posts.")
        if count is not None:
            count = _positive_integer(count, 'post count', minimum=0)
            if count < len(posts):
                raise GelbooruException("Gelbooru returned an invalid post count.")
        return posts, count

    async def get_post(self, post_id: int) -> Optional[GelbooruImage]:
        post_id = _positive_integer(post_id, 'post ID')
        endpoint = self._endpoint('post')
        endpoint.args['id'] = post_id
        posts, _ = self._parse_posts(await self._request(str(endpoint)))
        for payload in posts:
            post = GelbooruImage(payload, self)
            if post.id == post_id:
                return post
        raise GelbooruNotFoundException(f"Post {post_id} was not found.")

    async def random_post(self, *, tags: Optional[List[str]] = None,
                          exclude_tags: Optional[List[str]] = None) -> Optional[GelbooruImage]:
        tags = [tag for tag in self._format_tags(tags, exclude_tags) if not tag.startswith('sort:')]
        tags.append('sort:random')
        return await self.search_posts(tags=tags, limit=1, page=0)

    async def search_posts(self, *, tags: Optional[List[str]] = None,
                           exclude_tags: Optional[List[str]] = None,
                           limit: int = 100,
                           page: int = 0) -> Union[List[GelbooruImage], GelbooruImage, None]:
        limit = _positive_integer(limit, 'post limit', maximum=self.MAX_LIMIT)
        page = _positive_integer(page, 'page', minimum=0)
        endpoint = self._endpoint('post')
        endpoint.args['limit'] = limit
        endpoint.args['pid'] = page
        tags = self._format_tags(tags, exclude_tags)
        if tags:
            endpoint.args['tags'] = ' '.join(tags)
        posts, _ = self._parse_posts(await self._request(str(endpoint)))
        result = [GelbooruImage(payload, self) for payload in posts]
        return (result[0] if result else None) if limit == 1 else result

    def _endpoint(self, s: str) -> furl:
        endpoint = furl(self._base_url)
        endpoint.args['page'] = 'dapi'
        endpoint.args['s'] = s
        endpoint.args['q'] = 'index'
        if self._api_key:
            endpoint.args['api_key'] = self._api_key
        if self._user_id:
            endpoint.args['user_id'] = self._user_id
        return endpoint

    def _format_tags(self, tags: list, exclude_tags: list):
        result = []
        for values, excluded in ((tags, False), (exclude_tags, True)):
            if values is None:
                continue
            if isinstance(values, str):
                values = values.split(',')
            if not isinstance(values, (list, tuple, set)):
                raise GelbooruException("Invalid tags. Provide text tags separated by commas.")
            for value in values:
                if not isinstance(value, str) or any(ord(char) < 32 for char in value):
                    raise GelbooruException("Invalid tag.")
                value = '_'.join(value.strip().lower().split())
                if excluded:
                    value = value.lstrip('-')
                    value = '-' + value if value else ''
                if value and value not in result:
                    result.append(value)
        return result

    async def _request(self, url: str) -> bytes:
        proxy_url = self._get_proxy_settings()
        try:
            return await asyncio.wait_for(
                self._request_with_retries(url, proxy_url), timeout=self._timeout.total
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Gelbooru request timed out.") from None

    async def _request_with_retries(self, url, proxy_url):
        headers = {'Accept': 'application/xml, application/json', 'Accept-Encoding': 'gzip, deflate'}
        session_args = {'headers': headers}
        if self._display_all_content:
            session_args['cookies'] = {'fringeBenefits': 'yup'}
        if self._loop is not None:
            session_args['loop'] = self._loop
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(**session_args) as session:
                    status_code, response = await self._fetch(session, url, proxy=proxy_url)
            except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, OSError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                if isinstance(exc, asyncio.TimeoutError):
                    raise asyncio.TimeoutError("Gelbooru request timed out.") from None
                raise GelbooruException("Could not connect to Gelbooru. Check your connection and proxy settings.") from None
            except (aiohttp.ClientError, ValueError):
                raise GelbooruException("Gelbooru request failed. Check your connection and proxy settings.") from None
            if status_code in (200, 201):
                return response
            if status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if status_code in (401, 403):
                raise GelbooruException(f"Gelbooru HTTP {status_code}: access denied. Check the API key and user ID.")
            raise GelbooruException(f"Gelbooru HTTP {status_code}. Please try again later.")

    async def _fetch(self, session: aiohttp.ClientSession, url, proxy=None) -> Tuple[int, bytes]:
        async with session.get(url, timeout=self._timeout, proxy=proxy) as response:
            if response.content_length is not None and response.content_length > self.MAX_RESPONSE_BYTES:
                raise GelbooruException("Gelbooru response is too large.")
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                if len(data) + len(chunk) > self.MAX_RESPONSE_BYTES:
                    raise GelbooruException("Gelbooru response is too large.")
                data.extend(chunk)
            return response.status, bytes(data)


def _datetime(date: str, format='%a %b %d %H:%M:%S %z %Y') -> Optional[datetime]:
    if isinstance(date, datetime):
        return date
    if not isinstance(date, str) or not date.strip():
        return None
    try:
        return datetime.strptime(date, format)
    except ValueError:
        try:
            return datetime.fromisoformat(date.replace('Z', '+00:00'))
        except ValueError:
            return None
