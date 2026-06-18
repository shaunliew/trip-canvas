# TripCanvas Deployment

TripCanvas is deployed as two services:

- Frontend: Vercel, rooted at `frontend/`
- Backend: Render Web Service, rooted at the repo root

## 1. Deploy Backend On Render

Create a Render Blueprint from the repo root. Render will read `render.yaml`.

The backend service uses:

- Runtime: Python
- Build command: `uv sync --frozen --no-dev`
- Start command: `uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

Set these Render environment variables:

```bash
OPENAI_API_KEY=...
APIFY_TOKEN=...
USE_CACHE=true
CORS_ALLOW_ORIGINS=https://your-vercel-app.vercel.app
AP2_MODE=disabled
X402_MODE=simulation
HOTEL_BOOKING_MODE=mock
USE_MOCK_PAYMENT=true
```

`OPENAI_API_KEY` and `APIFY_TOKEN` are required for live Reel extraction and
planning. The cache/demo path can still serve `/demo-cache` with committed data.

After deploy, verify:

```bash
curl https://your-render-service.onrender.com/health
```

## 2. Deploy Frontend On Vercel

Import the same repo into Vercel and set the project root directory to:

```text
frontend
```

The frontend project uses `frontend/vercel.json`:

```bash
npm ci
npm run build
```

Set these Vercel environment variables:

```bash
NEXT_PUBLIC_MAPBOX_TOKEN=...
NEXT_PUBLIC_BACKEND_URL=https://your-render-service.onrender.com
```

After Vercel creates the production URL, update Render's
`CORS_ALLOW_ORIGINS` to that exact Vercel origin and redeploy the backend.

## 3. Smoke Test

Open the Vercel URL and test the reliable demo path first:

1. Click `Backend Cache`.
2. Confirm the map renders with cached places and itinerary.
3. Open the browser network panel and confirm `/demo-cache` returns 200 from
   the Render backend.

Then test live generation only after `OPENAI_API_KEY` and `APIFY_TOKEN` are set
on Render.
