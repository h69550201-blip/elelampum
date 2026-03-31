# Elelampum — Burst Bridge

Media search for **Lampa TV** powered by **Elementum Burst** provider definitions.  
No Jackett, no Jacred — self-contained search across 30+ public providers.

## Plugin URL

```
https://h69550201-blip.github.io/elelampum/burst_bridge.min.js
```

Add this URL in Lampa → Settings → Extensions.

## Architecture

```
┌─────────────┐        ┌──────────────────┐        ┌────────────┐
│  Lampa TV   │──API──▶│   Burst Bridge   │──HTTP──▶│  Provider  │
│  (plugin)   │◀─JSON──│   (FastAPI)      │◀─HTML───│   Sites    │
└─────────────┘        └──────────────────┘        └────────────┘
       │                                                    
       ▼               84 Elementum Burst provider defs     
┌─────────────┐        (fetched at runtime from GitHub)     
│ TorrServer  │                                             
└─────────────┘                                             
```

**Plugin** (`plugin/burst_bridge.js`) — JS loaded by Lampa, adds settings UI + media source  
**Backend** (`backend/`) — FastAPI server that scrapes provider sites using Burst definitions  
**providers.json** — fetched automatically at startup from Elementum GitHub repo

## Deployment

### Railway (auto-deploy via GitHub Actions)
Add `RAILWAY_TOKEN` secret to the repo, then every push auto-deploys.

### Docker
```bash
docker build -t burst-bridge .
docker run -p 8668:8668 burst-bridge
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
2. Add plugin URL in Lampa extensions
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
