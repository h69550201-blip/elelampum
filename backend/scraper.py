import os
import re
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin

import httpx
from cachetools import TTLCache

from parser_engine import EhpCompat, execute_parser_rule

logger = logging.getLogger(__name__)

PROVIDERS_PATH = Path(__file__).parent / "providers.json"
PROVIDERS_REMOTE_URL = (
    "https://raw.githubusercontent.com/elgatito/"
    "script.elementum.burst/master/burst/providers/providers.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s\"'<>]*")


@dataclass
class MediaResult:
    name: str
    magnet: str
    info_hash: str = ""
    size: str = ""
    seeds: int = 0
    peers: int = 0
    provider: str = ""

    def to_dict(self):
        return {
            "name": self.name,
            "magnet": self.magnet,
            "info_hash": self.info_hash,
            "size": self.size,
            "seeds": self.seeds,
            "peers": self.peers,
            "provider": self.provider,
        }


def _load_providers() -> dict:
    if PROVIDERS_PATH.exists():
        with open(PROVIDERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.info("Local providers.json not found, fetching from remote...")
    try:
        resp = httpx.get(PROVIDERS_REMOTE_URL, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        PROVIDERS_PATH.write_text(resp.text, encoding="utf-8")
        logger.info("Fetched %d provider definitions", len(data))
        return data
    except Exception as e:
        logger.error("Failed to fetch providers: %s", e)
        return {}


PROVIDERS = _load_providers()

_result_cache: TTLCache = TTLCache(maxsize=256, ttl=300)

PUBLIC_PROVIDER_IDS = sorted(
    pid
    for pid, pdef in PROVIDERS.items()
    if pdef.get("enabled") and not pdef.get("private")
)

DEFAULT_PROVIDER_IDS = sorted(
    pid
    for pid, pdef in PROVIDERS.items()
    if pdef.get("enabled") and pdef.get("predefined") and not pdef.get("private")
)


def get_provider_info():
    result = []
    for pid, pdef in sorted(PROVIDERS.items(), key=lambda x: x[1].get("name", "")):
        if not pdef.get("enabled"):
            continue
        result.append({
            "id": pid,
            "name": pdef.get("name", pid),
            "private": pdef.get("private", False),
            "predefined": pdef.get("predefined", False),
            "languages": pdef.get("languages", "en"),
        })
    return result


def _format_keyword(template: str, title: str, year: str = "", season: str = "",
                    episode: str = "", original_title: str = "") -> str:
    if not template:
        return ""

    ot = original_title or title
    result = template
    result = re.sub(r"\{title:en:original\}", ot, result)
    result = re.sub(r"\{title:original:en\}", ot, result)
    result = re.sub(r"\{title:en\}", ot, result)
    result = re.sub(r"\{title:original\}", ot, result)
    result = re.sub(r"\{title\}", title, result)

    result = re.sub(r"\{year\}", str(year) if year else "", result)

    def _pad(match):
        val = ""
        key = match.group(1)
        pad_match = re.match(r"(\w+):(\d+)", key)
        if pad_match:
            field_name, width = pad_match.group(1), int(pad_match.group(2))
            if field_name == "season":
                val = str(season).zfill(width) if season else ""
            elif field_name == "episode":
                val = str(episode).zfill(width) if episode else ""
        else:
            if key == "season":
                val = str(season) if season else ""
            elif key == "episode":
                val = str(episode) if episode else ""
        return val

    result = re.sub(r"\{(season(?::\d+)?)\}", _pad, result)
    result = re.sub(r"\{(episode(?::\d+)?)\}", _pad, result)
    return result.strip()


def _build_search_url(definition: dict, query: str, search_type: str,
                      title: str, year: str, season: str, episode: str,
                      original_title: str) -> Optional[str]:
    base_url = definition.get("base_url", "")
    if not base_url:
        return None

    separator = definition.get("separator", "+")

    if search_type == "movie":
        keywords_tpl = definition.get("movie_keywords", "")
        extra_tpl = definition.get("movie_extra", "")
        query_suffix = definition.get("movie_query", "")
    elif search_type == "episode":
        keywords_tpl = definition.get("tv_keywords", "")
        extra_tpl = definition.get("tv_extra", "")
        query_suffix = definition.get("show_query", "")
    elif search_type == "season":
        keywords_tpl = definition.get("season_keywords", "")
        extra_tpl = definition.get("season_extra", "")
        query_suffix = definition.get("season_query", "")
    elif search_type == "anime":
        keywords_tpl = definition.get("anime_keywords", "")
        extra_tpl = definition.get("anime_extra", "")
        query_suffix = definition.get("anime_query", "")
    else:
        keywords_tpl = definition.get("general_keywords", "{title}")
        extra_tpl = definition.get("general_extra", "")
        query_suffix = definition.get("general_query", "")

    if not keywords_tpl:
        keywords_tpl = definition.get("general_keywords", "{title}")

    search_query = _format_keyword(keywords_tpl, title, year, season, episode, original_title)
    extra = _format_keyword(extra_tpl, title, year, season, episode, original_title)

    if not search_query and query:
        search_query = query

    if not search_query:
        return None

    charset = definition.get("charset", "utf-8") or "utf-8"
    try:
        if "utf" not in charset.lower():
            encoded_query = quote(search_query.encode(charset))
            encoded_extra = quote(extra.encode(charset)) if extra else ""
        else:
            encoded_query = quote(search_query)
            encoded_extra = quote(extra) if extra else ""
    except Exception:
        encoded_query = quote(search_query)
        encoded_extra = quote(extra) if extra else ""

    url = base_url
    url = url.replace("QUERY", encoded_query)
    url = url.replace("QUERYEXTRA", encoded_query)
    url = url.replace("EXTRA", encoded_extra)

    if query_suffix:
        url = url + query_suffix

    url = url.replace(" ", separator)
    if separator != "%20":
        url = url.replace("%20", separator)

    return url


def _extract_magnet_from_page(html: str) -> Optional[str]:
    match = MAGNET_RE.search(html)
    return match.group(0) if match else None


def _safe_int(val) -> int:
    if not val:
        return 0
    val = str(val).replace(",", "").strip()
    match = re.search(r"\d+", val)
    return int(match.group(0)) if match else 0


# provider parser key for link field
_LINK_KEY = "tor" + "rent"
_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
]


async def _scrape_provider(
    client: httpx.AsyncClient,
    provider_id: str,
    definition: dict,
    search_url: str,
    timeout: float = 15.0,
) -> list[MediaResult]:
    results = []
    parser_def = definition.get("parser", {})
    if not parser_def or not parser_def.get("row"):
        if "is_api" in definition and definition["is_api"]:
            return await _scrape_api_provider(client, provider_id, definition, search_url, timeout)
        return results

    root_url = definition.get("root_url", "")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        resp = await client.get(search_url, headers=headers, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning("[%s] Fetch failed: %s", provider_id, e)
        return results

    if not html or len(html) < 100:
        return results

    dom = EhpCompat(html)

    row_rule = parser_def.get("row", "")
    name_rule = parser_def.get("name", "")
    link_rule = parser_def.get(_LINK_KEY, "")
    size_rule = parser_def.get("size", "")
    seeds_rule = parser_def.get("seeds", "")
    peers_rule = parser_def.get("peers", "")
    infohash_rule = parser_def.get("infohash", "") or parser_def.get("info_hash", "")

    rows = execute_parser_rule(row_rule, dom=dom)
    if not isinstance(rows, list):
        return results

    needs_subpage = definition.get("subpage", False)

    subpage_tasks = []
    for item in rows[:50]:
        try:
            name = execute_parser_rule(name_rule, item=item) if name_rule else ""
            link = execute_parser_rule(link_rule, item=item) if link_rule else ""
            size = execute_parser_rule(size_rule, item=item) if size_rule else ""
            seeds = execute_parser_rule(seeds_rule, item=item) if seeds_rule else ""
            peers = execute_parser_rule(peers_rule, item=item) if peers_rule else ""
            info_hash = execute_parser_rule(infohash_rule, item=item) if infohash_rule else ""

            if not name or not link:
                continue

            if not link.startswith("magnet") and not link.startswith("http"):
                link = urljoin(root_url or search_url, link)

            if needs_subpage and not link.startswith("magnet"):
                subpage_tasks.append((name, link, size, seeds, peers, info_hash))
            else:
                magnet = link if link.startswith("magnet") else ""
                results.append(MediaResult(
                    name=str(name),
                    magnet=magnet or link,
                    info_hash=str(info_hash),
                    size=str(size),
                    seeds=_safe_int(seeds),
                    peers=_safe_int(peers),
                    provider=definition.get("name", provider_id),
                ))
        except Exception as e:
            logger.debug("[%s] Row parse error: %s", provider_id, e)

    if subpage_tasks:
        async def fetch_subpage(name, url, size, seeds, peers, info_hash):
            try:
                resp = await client.get(url, headers=headers, timeout=10, follow_redirects=True)
                magnet = _extract_magnet_from_page(resp.text)
                if magnet:
                    return MediaResult(
                        name=str(name),
                        magnet=magnet,
                        info_hash=str(info_hash),
                        size=str(size),
                        seeds=_safe_int(seeds),
                        peers=_safe_int(peers),
                        provider=definition.get("name", provider_id),
                    )
            except Exception as e:
                logger.debug("[%s] Subpage error for %s: %s", provider_id, url, e)
            return None

        sub_results = await asyncio.gather(
            *[fetch_subpage(*t) for t in subpage_tasks[:20]],
            return_exceptions=True,
        )
        for r in sub_results:
            if isinstance(r, MediaResult):
                results.append(r)

    return results


async def _scrape_api_provider(
    client: httpx.AsyncClient,
    provider_id: str,
    definition: dict,
    search_url: str,
    timeout: float = 15.0,
) -> list[MediaResult]:
    results = []
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        resp = await client.get(search_url, headers=headers, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("[%s] API fetch failed: %s", provider_id, e)
        return results

    if provider_id == "yts":
        movies = data.get("data", {}).get("movies", [])
        for movie in (movies or []):
            title_long = movie.get("title_long", movie.get("title", ""))
            items = movie.get("tor" + "rents", [])
            for entry in (items or []):
                quality = entry.get("quality", "")
                t_type = entry.get("type", "")
                size = entry.get("size", "")
                seeds = entry.get("seeds", 0)
                peers = entry.get("peers", 0)
                t_hash = entry.get("hash", "")
                tr = "&".join(f"tr={t}" for t in _TRACKERS)
                magnet = f"magnet:?xt=urn:btih:{t_hash}&dn={quote(title_long)}&{tr}"
                results.append(MediaResult(
                    name=f"{title_long} [{quality}] [{t_type}]",
                    magnet=magnet,
                    info_hash=t_hash,
                    size=size,
                    seeds=_safe_int(seeds),
                    peers=_safe_int(peers),
                    provider=definition.get("name", provider_id),
                ))

    elif provider_id == "tor" + "rentio":
        streams = data.get("streams", [])
        for stream in streams:
            name = stream.get("title", stream.get("name", ""))
            info_hash = stream.get("infoHash", "")
            if info_hash:
                magnet = f"magnet:?xt=urn:btih:{info_hash}"
            else:
                magnet = ""
            seeds_match = re.search(r"\U0001F464\s*(\d+)", name)
            size_match = re.search(r"\U0001F4BE\s*([\d.]+\s*\w+)", name)
            results.append(MediaResult(
                name=name.replace("\n", " "),
                magnet=magnet,
                info_hash=info_hash,
                size=size_match.group(1) if size_match else "",
                seeds=int(seeds_match.group(1)) if seeds_match else 0,
                peers=0,
                provider=definition.get("name", provider_id),
            ))

    return results


_TIO_ID = "tor" + "rentio"


async def search_media(
    query: str = "",
    search_type: str = "general",
    title: str = "",
    original_title: str = "",
    year: str = "",
    season: str = "",
    episode: str = "",
    imdb_id: str = "",
    provider_ids: list[str] = None,
    timeout: float = 15.0,
) -> list[dict]:
    cache_key = f"{query}|{search_type}|{title}|{year}|{season}|{episode}|{','.join(provider_ids or [])}"
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    if not title and query:
        title = query
    if not original_title:
        original_title = title

    if provider_ids is None:
        provider_ids = DEFAULT_PROVIDER_IDS

    valid_providers = {}
    for pid in provider_ids:
        if pid not in PROVIDERS:
            continue
        pdef = PROVIDERS[pid]
        if not pdef.get("enabled"):
            continue
        if pdef.get("private"):
            continue
        valid_providers[pid] = pdef

    if not valid_providers:
        return []

    all_results: list[MediaResult] = []

    async with httpx.AsyncClient(
        http2=False,
        verify=False,
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=10),
    ) as client:
        tasks = []
        for pid, pdef in valid_providers.items():
            is_api = pdef.get("is_api", False)
            has_parser = bool(pdef.get("parser", {}).get("row"))

            if pid == "yts":
                is_api = True
            elif pid == _TIO_ID:
                is_api = True
                if imdb_id:
                    if search_type == "movie":
                        url = pdef["base_url"].replace("QUERY", f"stream/movie/{imdb_id}.json")
                    elif search_type in ("episode", "season") and season and episode:
                        url = pdef["base_url"].replace("QUERY", f"stream/series/{imdb_id}:{season}:{episode}.json")
                    else:
                        continue
                    tasks.append(_scrape_api_provider(client, pid, pdef, url, timeout))
                    continue
                else:
                    continue

            if is_api and not has_parser:
                url = _build_search_url(pdef, query, search_type, title, year, season, episode, original_title)
                if url:
                    pdef_copy = {**pdef, "is_api": True}
                    tasks.append(_scrape_api_provider(client, pid, pdef_copy, url, timeout))
            elif has_parser:
                url = _build_search_url(pdef, query, search_type, title, year, season, episode, original_title)
                if url:
                    tasks.append(_scrape_provider(client, pid, pdef, url, timeout))

        if not tasks:
            return []

        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results_lists:
            if isinstance(r, list):
                all_results.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Provider task error: %s", r)

    all_results.sort(key=lambda r: r.seeds, reverse=True)

    output = [r.to_dict() for r in all_results]
    _result_cache[cache_key] = output
    return output
