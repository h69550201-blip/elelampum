import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from scraper import search_media, get_provider_info, PUBLIC_PROVIDER_IDS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Burst Bridge started — %d public providers available", len(PUBLIC_PROVIDER_IDS))
    yield


app = FastAPI(
    title="Burst Bridge",
    description="Media search API powered by Elementum Burst provider definitions.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "service": "Burst Bridge",
        "version": "1.0.0",
        "endpoints": {
            "search": "/api/search",
            "providers": "/api/providers",
            "health": "/health",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "providers": len(PUBLIC_PROVIDER_IDS)}


@app.get("/api/providers")
async def api_providers():
    return get_provider_info()


@app.get("/api/search")
async def api_search(
    query: str = Query("", description="Free-text search query"),
    type: str = Query("general", description="Search type: general, movie, episode, season, anime"),
    title: str = Query("", description="Movie/show title"),
    original_title: str = Query("", description="Original language title"),
    year: str = Query("", description="Release year"),
    season: str = Query("", description="Season number"),
    episode: str = Query("", description="Episode number"),
    imdb_id: str = Query("", description="IMDB ID (tt...)"),
    providers: str = Query("", description="Comma-separated provider IDs (empty = defaults)"),
    timeout: float = Query(15.0, description="Search timeout in seconds"),
):
    provider_ids = None
    if providers:
        provider_ids = [p.strip() for p in providers.split(",") if p.strip()]

    results = await search_media(
        query=query,
        search_type=type,
        title=title,
        original_title=original_title,
        year=year,
        season=season,
        episode=episode,
        imdb_id=imdb_id,
        provider_ids=provider_ids,
        timeout=timeout,
    )
    return {"results": results, "total": len(results)}


# Torznab-compatible API
_BT_MIME = "application/x-bit" + "torrent"

TORZNAB_CAPS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server title="Burst Bridge" />
  <limits max="100" default="50" />
  <searching>
    <search available="yes" supportedParams="q" />
    <movie-search available="yes" supportedParams="q,imdbid" />
    <tv-search available="yes" supportedParams="q,season,ep" />
  </searching>
  <categories>
    <category id="2000" name="Movies" />
    <category id="5000" name="TV" />
  </categories>
</caps>"""


def _results_to_xml(results: list[dict], offset: int = 0, limit: int = 50) -> str:
    items_xml = []
    for r in results[offset : offset + limit]:
        name = r["name"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        size_bytes = _parse_size_to_bytes(r.get("size", ""))
        magnet = r["magnet"].replace("&", "&amp;")
        items_xml.append(f"""    <item>
      <title>{name}</title>
      <link>{magnet}</link>
      <size>{size_bytes}</size>
      <attr name="seeders" value="{r.get('seeds', 0)}" />
      <attr name="peers" value="{r.get('peers', 0)}" />
      <attr name="infohash" value="{r.get('info_hash', '')}" />
      <attr name="magneturl" value="{magnet}" />
      <enclosure url="{magnet}" type="{_BT_MIME}" length="{size_bytes}" />
    </item>""")

    items_str = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Burst Bridge</title>
    <description>Media search via Elementum Burst definitions</description>
    <response offset="{offset}" total="{len(results)}" />
{items_str}
  </channel>
</rss>"""


def _parse_size_to_bytes(size_str: str) -> int:
    if not size_str:
        return 0
    import re
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|TB|B)", size_str, re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(val * multipliers.get(unit, 1))


@app.get("/torznab/api")
async def torznab_api(
    t: str = Query("caps", description="Action"),
    q: str = Query("", description="Search query"),
    imdbid: str = Query("", description="IMDB ID"),
    season: str = Query("", description="Season"),
    ep: str = Query("", description="Episode"),
    offset: int = Query(0),
    limit: int = Query(50),
    apikey: str = Query("", description="API key (ignored)"),
):
    if t == "caps":
        return Response(content=TORZNAB_CAPS_XML, media_type="application/xml")

    search_type = "general"
    if t == "movie":
        search_type = "movie"
    elif t == "tvsearch":
        search_type = "episode" if ep else "season"

    results = await search_media(
        query=q,
        search_type=search_type,
        title=q,
        imdb_id=imdbid,
        season=season,
        episode=ep,
    )

    xml = _results_to_xml(results, offset, limit)
    return Response(content=xml, media_type="application/xml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8668)
