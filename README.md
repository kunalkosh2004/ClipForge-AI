# ClipForge AI

An AI-powered Video Intelligence Platform that automatically turns long-form videos into viral-ready short-form content (reels / Shorts / TikTok). It transcribes your video, understands the content with an AI Director, cuts the best moments into clips, and renders them with animated motion captions, color grading, sound effects, and smart 9:16 re-framing. Competes with Opus Clip, Captions AI, Vizard, Klap, and Munch.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Tech stack](#tech-stack)
3. [Quick start](#quick-start)
4. [How to use the app](#how-to-use-the-app)
5. [Background pipeline](#background-pipeline)
6. [Timing & expectations](#timing--expectations)
7. [Accuracy](#accuracy)
8. [API reference](#api-reference)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Project structure](#project-structure)
12. [Troubleshooting](#troubleshooting)
13. [Known limitations](#known-limitations)

---

## How it works

```
 Upload / YouTube URL
        │
        ▼
┌───────────────────┐   ffprobe: duration, resolution, codecs, checksum
│ metadata          │
└─────────┬─────────┘
          ▼
┌───────────────────┐   Gemini (chunked, word-level transcription)
│ AI analysis       │   ├─ transcript (words + segments, timestamps)
│                   │   ├─ video understanding (scenes, topics, sentiment)
│                   │   ├─ editing plan (best clips with scores)
│                   │   ├─ preset recommendation (motivational, podcast, …)
│                   │   └─ editing blueprint (AI Director: themes, glow,
│                   │      camera moves, SFX, transitions)
└─────────┬─────────┘
          ▼
┌───────────────────┐   FFmpeg: cut each candidate clip + thumbnail
│ clip extraction   │   format: 9:16 / 16:9 / original (from preset or prompt)
└─────────┬─────────┘
          ▼
┌───────────────────┐   FFmpeg + MotionCaption engine
│ render            │   ├─ animated captions (frames/ASS) with karaoke
│                   │   ├─ face-aware caption placement (YuNet)
│                   │   ├─ smart 9:16 re-framing (face + motion tracking)
│                   │   ├─ color grading (glow / bloom / contrast / vignette)
│                   │   └─ music bed, beat-timed SFX, emoji, CTA overlays
└─────────┬─────────┘
          ▼
    Ready clips + transcript + subtitles (SRT/VTT) + AI usage dashboard
```

Every stage runs as a **Dramatiq background job** (Redis broker) with retries, exponential backoff, dead-letter handling, and real-time status streamed to the frontend over Server-Sent Events.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16, Redis 7 |
| Queue | Dramatiq (Redis broker, dedicated `metadata` / `ai` / `render` / `media` queues) |
| AI | Google Gemini (`google-genai` SDK) with API-key + model fallback chains, and a Mock provider for offline dev |
| Video | FFmpeg / FFprobe (metadata, cutting, compositing, thumbnails) |
| Captions | Vendored **MotionCaption 0.1.3** engine (bundled Noto Sans fonts) — frame-based and ASS backends |
| Intelligence | Scene / Motion / Beat / Timeline artifact workers (PySceneDetect, librosa, OpenCV YuNet face detection) |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS 4 |
| Auth | JWT (access + refresh), Argon2 password hashing |
| Infra | Docker Compose, Makefile |
| Observability | structlog, OpenTelemetry tracing, Prometheus metrics, AI usage tracking |

---

## Quick start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (only needed for local backend tooling/tests)
- Node.js 18+ (for the frontend)
- A **Google Gemini API key** (get one at https://aistudio.google.com/apikey) — required for real AI analysis

### 1. Configure the API key

```bash
cd backend
cp .env.example .env
# edit .env and set:
#   GEMINI_API_KEY=your-gemini-api-key
```

You can also add `GEMINI_API_KEYS=key2,key3` as a fallback chain (each key gets its own daily quota — tried in order when one fails or is exhausted).

> No key? Set `AI_PROVIDER=mock` in `.env` to run the pipeline with a deterministic mock AI (no transcription/analysis quality — for development only).

### 2. Start the stack

```bash
make up          # starts postgres, redis, api (:8000), worker
make migrate     # run database migrations
make seed        # creates demo user: demo@clipforge.ai / demo1234
```

Services:

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:3000 (start separately, step 3) |
| API      | http://localhost:8000 |
| Swagger  | http://localhost:8000/docs |
| Postgres | `localhost:5436` (`clipforge`/`clipforge`) |
| Redis    | `localhost:6382` |

### 3. Start the frontend

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000**, log in with `demo@clipforge.ai` / `demo1234` (or register a new account).

### 4. Verify

```bash
make ps         # all 4 containers healthy
curl http://localhost:8000/api/v1/health
```

---

## How to use the app

### 1. Sign in

- Go to http://localhost:3000 → **Register** a new account (or **Login** with the seeded demo user).
- Your JWT is stored in the browser; the frontend auto-refreshes it when it expires.

### 2. Create a project

On the dashboard, click **New Project**, give it a name (e.g. `Timeless Reels`). A project is a container for videos.

### 3. Add a video — two ways

**A. Upload a file** — pick a video (MP4/MOV, up to 1 GiB). The file is uploaded to local storage via a signed URL, then processing starts.

**B. Paste a YouTube URL** — the worker downloads it with yt-dlp (watch, shorts, embed, live, and youtu.be links all work).

### 4. (Optional) Set an editing prompt

Before processing, set a prompt that describes the output you want. The AI Director honors it — this is how you control format, style, and captions. Examples that work:

```
Make this a vertical 9:16 reel for TikTok/Shorts. Output format MUST be
portrait 9:16 (1080x1920). Use the motivational preset with glowing captions
and a dark moody cinematic grade.
```

The Director picks a **preset** from 12 built-in styles — `podcast`, `storytelling`, `tutorial`, `reaction`, `commentary`, `motivational`, `mrbeast`, `hormozi`, `minimal`, `gaming`, `documentary`, `business` (each defines caption style, zoom, transitions, overlays, and audio). The preset determines output format:
- `9:16` (1080×1920 portrait) for most presets — reels/Shorts
- `16:9` (1920×1080 landscape) for `podcast` and `documentary`
- `original` (source dimensions) for `minimal` or when no preset applies

### 5. Process

Click **Process**. The video moves through `metadata → ai_analysis → clip_extraction → render`. You'll see live status (stage + message) streamed to the page. You can close the tab; the worker continues.

### 6. Review results

On the video detail page you get:
- **Transcript** — word-level, timestamped (JSON)
- **AI analysis** — understanding, editing plan, recommended preset
- **Clips** — one row per extracted clip, with title, time range, format, thumbnail, and download
- **Subtitles** — export the transcript as **SRT** or **VTT**
- **Timeline** — the compiled event timeline for the video

### 7. Download

Download individual rendered clips, or grab all clips as a ZIP. Clips are the final short-form videos (with captions + grading baked in).

> Tip: an **AI usage bar** in the dashboard header shows your daily Gemini token/request usage per API key.

---

## Background pipeline

Four job stages run in order; each success enqueues the next (Dramatiq actors in `backend/src/clipforge/worker/tasks.py`):

| # | Stage | What happens | Runtime |
|---|-------|-------------|---------|
| 1 | `metadata_extraction` | ffprobe → duration, resolution, fps, codecs; SHA-256 checksum | seconds |
| 2 | `ai_analysis` | Gemini: word-level transcription + video understanding + editing plan + preset + Director blueprint | **longest** (see below) |
| 3 | `clip_extraction` | FFmpeg cuts each clip (H.264/AAC, CRF 23, faststart) + thumbnail | ~1–3 min |
| 4 | `render` | captions, grading, framing, SFX, music → final MP4 per clip | ~1–2 min / clip |

**Transcription (stage 2, the slow part):** audio is extracted to a mono 16 kHz WAV and transcribed in **45-second chunks with 3 s overlap**. Chunking keeps Gemini's word timestamps reliable on multi-minute videos (single-shot transcription drifts and can silently drop whole sections). The merge drops each chunk's overlap head, caps implausibly long words, clamps timestamps to the real duration, and **re-transcribes any silent gap > 8 s** so captions never desync.

**Intelligence artifacts (parallel):** `POST /videos/{id}/intelligence/start` runs the artifact workers (`metadata`, `scene`, `motion`, `beat`, `timeline`) through a workflow DAG, each writing versioned JSON artifacts consumed by the renderer.

**Rendering details:**
- Caption engine: `frames` (default — MotionCaption renders animated RGBA caption frames, baked fonts from the bundled Noto Sans) or `ass` / `legacy`
- Captions are placed **face-aware** (YuNet ONNX face detection steers captions off faces)
- **9:16 smart re-framing** tracks the subject (face + motion center-of-mass) and glides a crop window along it
- **Color grading** from the blueprint's `global_style` — brightness, contrast, temperature, vignette, film grain, and **glow/bloom** (screen-blend highlight pass)
- Music bed + beat-timed SFX, emoji triggers, CTA overlays, punch zooms

**Failure handling:** 5 attempts per stage with exponential backoff; on exhaustion the job goes to a Redis dead-letter store (inspectable via the admin API) and the video is marked `failed` with a readable message.

---

## Timing & expectations

Measured end-to-end on a 4:16 (256 s), 1920×1080 source with 5 output clips (MacBook, single worker):

| Video length | AI analysis | Clip extraction | Render (5 clips) | **Total** |
|--------------|-------------|-----------------|------------------|-----------|
| ~30 s | ~1–2 min | ~30 s | ~2–4 min | **~4–7 min** |
| ~1 min | ~3–5 min | ~1 min | ~3–5 min | **~8–12 min** |
| ~4 min (song) | ~15–25 min | ~2–3 min | ~5–10 min | **~25–35 min** |
| ~10 min (podcast) | ~30–45 min | ~3–5 min | ~10–20 min | **~45–70 min** |

Guidelines:

- **AI analysis dominates the time** — it's a function of video length (one Gemini call per 45 s chunk, plus the director/plan calls). Expect roughly **4–6 min of analysis per minute of video**.
- The exact time depends on Gemini load (transient 503s are retried automatically via the fallback chain) and your machine's CPU for the ffmpeg/face-tracking stages.
- Rendering scales with **number of clips**, not video length (roughly 1–2 min per 30 s clip).
- Watching `docker logs clipforge-worker-1 -f` shows live per-stage progress.

---

## Accuracy

**Transcription (word-level timestamps):**

- Designed so captions stay **synced to the audio**. The chunked approach exists because a single Gemini pass over a long video drifted and dropped speech — a 256 s video once produced a transcript with a **160 s hole**. Since the fix, a full-song transcript covered **100 % of the audio (0–240.8 s of 256 s)** with words present in every 20 s bucket.
- Silent gaps > 8 s are detected and **re-transcribed** (with margin) and spliced in, so dropped chunks self-heal.
- Word end-times are capped (Gemini occasionally stretches a 0.2 s word across 40 s) and everything is clamped to the real media duration — captions never outlive the video.
- Transcript quality is bounded by Gemini's ASR (English primarily; other languages follow Gemini support). For best results use clear speech, no heavy background music.

**Clip selection (AI Director):**

- Clips are picked by Gemini with a `viral_score`, grounded in scene/topic understanding, then **normalized deterministically** (clip count + durations clamped to the real video length — no made-up timestamps).
- A requested editing prompt (e.g. "9:16 motivational reel") measurably steers the preset choice — verified: prompt → `motivational` preset (0.8 confidence) → all clips `9:16`.

**Rendering fidelity:**

- Output dimensions are exact: 1080×1920 (9:16) / 1920×1080 (16:9) verified by ffprobe.
- 307 unit tests cover the pipeline (blueprint parsing, plugin filters, transcript merge/gap-fill, caption engines, font loading) — regression-tested, so sync/caption regressions get caught.

---

## API reference

Base URL: `http://localhost:8000/api/v1`. Interactive docs: `http://localhost:8000/docs`.

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register, returns access + refresh JWT |
| POST | `/auth/login` | Login (`{email, password}`) |
| POST | `/auth/refresh` | Refresh the access token |
| GET | `/auth/me` | Current user |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create project |
| GET | `/projects` | List projects (paginated) |
| DELETE | `/projects/{id}` | Delete project (cascade) |
| GET | `/projects/{id}/videos` | List videos in project |
| GET | `/projects/{id}/clips` | List clips in project |

### Videos
| Method | Path | Description |
|--------|------|-------------|
| POST | `/videos` | Start upload → returns signed upload URL |
| POST | `/videos/{id}/complete` | Complete upload, enqueue processing |
| PATCH | `/videos/{id}` | Set editing prompt (`editing_style`) |
| POST | `/videos/{id}/process` | (Re)start the full pipeline |
| GET | `/videos/{id}` | Get video |
| DELETE | `/videos/{id}` | Delete video |
| POST | `/videos/import` | Import from YouTube URL |
| POST | `/videos/{id}/intelligence/start` | Run artifact intelligence workers |
| GET | `/videos/{id}/stream` | SSE live status stream |

### Analysis, Clips & Timeline
| Method | Path | Description |
|--------|------|-------------|
| GET | `/presets` | List editing presets |
| GET | `/videos/{id}/transcript` | Word-level transcript (JSON) |
| GET | `/videos/{id}/analysis` | Understanding + editing plan + blueprint |
| GET | `/videos/{id}/subtitles?format=srt\|vtt` | Download subtitles |
| GET | `/videos/{id}/clips` | List clips |
| GET | `/videos/{id}/timeline` | Compiled event timeline |
| GET | `/clips/{id}` | Get clip |
| GET | `/clips/{id}/download` | Signed download URL for rendered clip |
| DELETE | `/clips/{id}` | Delete clip |
| GET | `/ai/usage` | Today's Gemini token/request usage per key |

### Admin (admin user role)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/jobs` | List pipeline jobs with status/errors |
| POST | `/admin/jobs/{id}/retry` | Requeue a job |
| GET | `/admin/dead-letters` | List dead-lettered messages |
| POST | `/admin/dead-letters/{id}/retry` | Requeue a dead letter |
| DELETE | `/admin/dead-letters/{id}` | Drop a dead letter |

### Infra
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/storage/{key}?action=…&token=…` | HMAC-signed storage read/write |
| GET | `/docs` | Swagger UI |

---

## Configuration

Backend settings come from `backend/.env` (see `backend/.env.example`):

| Key | Default | Purpose |
|-----|---------|---------|
| `GEMINI_API_KEY` | — | Primary Gemini key (required for real AI) |
| `GEMINI_API_KEYS` | — | Comma-separated fallback keys (per-key quota) |
| `GEMINI_MODEL` | `gemini-flash-latest` | Primary model (fallback chain built-in) |
| `GEMINI_DAILY_TOKEN_LIMIT` | `200000` | Daily token quota shown in usage bar |
| `GEMINI_DAILY_REQUEST_LIMIT` | `20` | Daily request quota per key |
| `AI_PROVIDER` | `gemini` | `gemini` or `mock` (offline dev) |
| `DATABASE_URL` | `postgresql+asyncpg://clipforge:clipforge@localhost:5436/clipforge` | App DB (compose overrides inside the network) |
| `REDIS_URL` | `redis://localhost:6382/0` | Broker + Pub/Sub + rate limiting |
| `JWT_SECRET` | dev secret | Token signing (change in production) |
| `STORAGE_BACKEND` / `STORAGE_ROOT` | `local` / `./storage` | Media storage (local disk; S3 planned) |
| `CAPTION_ENGINE` | `frames` | `frames` (default) / `ass` / `legacy` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Host used in signed URLs |
| `LOG_LEVEL` | `INFO` | structlog verbosity |

---

## Testing

```bash
# All tests (unit + API integration; API tests need the Docker stack up)
cd backend && .venv/bin/pytest tests/ -v

# Unit tests only (no Docker needed) — 307 passing
cd backend && .venv/bin/pytest tests/unit/ -v

# API integration tests (needs Docker)
cd backend && .venv/bin/pytest tests/api/ -v

# Lint + types
cd backend && .venv/bin/ruff check src tests && .venv/bin/mypy src
```

Coverage highlights: blueprint parsing (incl. AI `null`-field coercion), transcript chunk-merge + gap-fill, Gemini provider fallback chains, plugin filter emission (incl. glow/bloom), caption/font loading, rendering service, auth, pagination.

---

## Project structure

```
ClipForge-AI/
├── backend/                  # Python 3.12, FastAPI, Clean Architecture
│   ├── src/clipforge/
│   │   ├── api/              # FastAPI app, middleware (rate limit), DI
│   │   ├── identity/         # Auth (register, login, JWT, Argon2)
│   │   ├── videos/           # Projects, uploads, YouTube import, prompts
│   │   ├── analysis/         # AI analysis, presets, transcripts, subtitles
│   │   ├── directing/        # AI Director: editing blueprint + prompt
│   │   ├── clips/            # Clip extraction, thumbnails, delivery
│   │   ├── rendering/        # Composite renderer, captions, framing, zoom
│   │   ├── plugins/          # Plugin pipeline: subtitle, color, camera,
│   │   │                     #   transition, emoji, sfx, music, cta, overlay
│   │   ├── lyrics/           # MotionCaption bridge (frames/ASS engines)
│   │   ├── intelligence/     # Artifact workers (metadata/scene/motion/beat)
│   │   ├── timeline/         # Compiled event timeline API
│   │   ├── workflow/         # Artifact DAG orchestration
│   │   ├── artifacts/        # Versioned artifact store
│   │   ├── processing/       # Job tracking, status streaming
│   │   ├── ai/               # GeminiProvider (chunked ASR, fallback chains)
│   │   ├── storage/          # Local storage + signed URLs
│   │   ├── worker/           # Dramatiq pipeline actors
│   │   ├── usage/ admin/     # AI usage dashboard, admin (jobs/dead letters)
│   │   └── common/ db/       # Ports, errors, IDs; SQLAlchemy models
│   ├── tests/                # 307 unit + API tests
│   ├── alembic/              # Migrations
│   ├── vendor/               # Vendored motion-caption wheel (bundled fonts)
│   └── Dockerfile            # ffmpeg + fonts-noto-core + YuNet ONNX + deno
├── frontend/                 # Next.js 15 app (dashboard, upload, viewer)
├── infra/                    # docker-compose (postgres, redis, api, worker)
├── docs/                     # architecture + flow deep-dives
└── Makefile                  # up/down/logs/migrate/seed/lint/frontend
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| API key rejected / `401` | Check `GEMINI_API_KEY` in `backend/.env`, then `make up` (or `docker compose -f infra/docker-compose.yml restart api worker`) — containers load `.env` at start |
| Gemini `503` / rate limited | Transient — the fallback chain retries automatically. Add more keys to `GEMINI_API_KEYS` or wait |
| Video stuck on a stage | `docker logs clipforge-worker-1 -f`; inspect job rows via `GET /admin/jobs`; dead-lettered jobs via `GET /admin/dead-letters` |
| No captions in output | Confirm the worker image has fonts (`fonts-noto-core` is installed in the Dockerfile; the vendored MotionCaption wheel bundles Noto Sans). Check `CAPTION_ENGINE` |
| Ports busy | Postgres uses `5436` and Redis `6382` deliberately (avoid conflicts with local Postgres/Redis) |
| Frontend can't reach API | Frontend runs on `:3000`, API on `:8000` — check `frontend/.env.local` for the API base URL |

---

## Known limitations

- **Storage**: local disk only (S3 provider is planned).
- **Uploads**: single PUT, 1 GiB ceiling (multipart/resumable planned).
- **Transcription**: English-first, quality bounded by Gemini ASR; noisy audio reduces word-timestamp accuracy (the gap-fill handles dropped chunks, not misheard words).
- **Rendering**: the 9:16 smart-crop tracks a single subject (no multi-object selection yet); captions are auto-placed (no per-clip caption editor UI yet).
- **Frontend**: functional but minimal — no timeline editor, clip approval flow, or caption restyling UI yet.

---

## License

MIT
