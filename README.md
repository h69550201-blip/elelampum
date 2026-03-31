# Elelampum — Burst Bridge

Torrent search for **Lampa TV** powered by **Elementum Burst** provider definitions.  
No Jackett, no Jacred — self-contained search across 30+ public torrent providers.

## Plugin URL

After GitHub Actions deploys, the plugin is available at:

```
https://h69550201-blip.github.io/elelampum/burst_bridge.min.js
```

Add this URL in Lampa → Settings → Extensions.

## Architecture

```
┌─────────────┐        ┌──────────────────┐        ┌────────────┐
│  Lampa TV   │──API──▶│   Burst Bridge   │──HTTP──▶│  Torrent   │
│  (plugin)   │◀─JSON──│   (FastAPI)      │◀─HTML───│   Sites    │
└─────────────┘        └──────────────────┘        └────────────┘
       │                                                    
       ▼               84 Elementum Burst provider defs     
┌─────────────┐                                             
│ TorrServer  │                                             
└─────────────┘                                             
```

**Plugin** (`plugin/burst_bridge.js`) — JS loaded by Lampa, adds settings UI + torrent source  
**Backend** (`backend/`) — FastAPI server that scrapes torrent sites using Burst definitions

## Backend Deployment

### Docker
```bash
docker build -t burst-bridge .
docker run -p 8668:8668 burst-bridge
```

### Railway
```bash
railway up
```

### Manual
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8668
```

## Lampa Setup

### Option 1: Plugin + Backend
1. Deploy the backend (note the URL)
2. Add plugin URL in Lampa extensions: `https://h69550201-blip.github.io/elelampum/burst_bridge.min.js`
3. Go to Settings → Burst Bridge → set your backend URL

### Option 2: Torznab (no plugin needed)
Set `https://your-backend/torznab/api` as the parser URL in Lampa settings.

## API

| Endpoint | Description |
|---|---|
| `GET /api/search?query=...&type=movie&title=...&year=...` | JSON search |
| `GET /api/providers` | List providers |
| `GET /torznab/api?t=caps` | Torznab capabilities |
| `GET /torznab/api?t=movie&q=...&imdbid=...` | Torznab search |
| `GET /health` | Health check |

## Tested Providers

| Provider | Status |
|---|---|
| YTS | ✅ |
| The Pirate Bay | ✅ |
| Knaben | ✅ |
| LimeTorrents | ✅ |
| TorrentDownloads | ✅ |
| Torrentio | ✅ (needs IMDB ID) |
