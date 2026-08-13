# ClipForge AI — System Flow (Detailed)

This document describes, end-to-end, how ClipForge AI works today: the runtime
services, the request paths, the background processing pipeline, and how state
flows from upload to downloadable clips.

> Status: captures the implementation as of the latest commit
> (M5 — smart 9:16 re-framing: YuNet face + motion tracking crop).

---

## 1. System Topology

```
                        ┌──────────────┐
   Browser (Next.js) ──▶│  API :8000   │◀── PostgreSQL :5436
                        │   FastAPI    │◀── Redis :6382
                        └──────┬───────┘
                               │ enqueue
                               ▼
                        ┌──────────────┐
                        │  Worker      │  Dramatiq consumer
                        │  (dramatiq)  │
                        └──────┬───────┘
                               │
                    ┌──────────┼─────────────┐
                    ▼          ▼             ▼
                 FFprobe    FFmpeg      Gemini / Mock AI
                 (metadata) (cut clips) (analysis)
```

Three long-running processes (all started via `make up` → `docker-compose.yml`):

| Service   | Command                                   | Role                                     |
|-----------|-------------------------------------------|------------------------------------------|
| `postgres`| postgres:16-alpine                        | Source of truth (SQLAlchemy 2 + Alembic) |
| `redis`   | redis:7-alpine (appendonly)               | Queue broker + Pub/Sub + rate limiting   |
| `api`     | `uvicorn clipforge.api.main:app`          | REST + SSE endpoints                     |
| `worker`  | `dramatiq clipforge.worker.tasks`         | Background pipeline actors               |

The **frontend** (`frontend/`, Next.js 15) runs separately with `npm run dev`
on port 3000 and talks to the API on port 8000.

---

## 2. Ports & Provider Abstraction

All infrastructure dependencies are behind protocol interfaces
(`backend/src/clipforge/common/ports/`), swapped at wiring time by the DI
container (`backend/src/clipforge/container.py`).

| Port                       | Implementations                                  | Chosen by                          |
|----------------------------|--------------------------------------------------|------------------------------------|
| `StorageProvider`          | `LocalStorageProvider`, (S3 planned)             | `storage_backend` setting          |
| `QueueBroker`              | `DramatiqBroker`                                 | always                             |
| `CacheProvider`            | `InMemoryCache` (test), `RedisCache`             | `app_env == "test"`                |
| `AIProvider`               | `GeminiProvider`, `MockAIProvider`               | `ai_provider` / API key presence   |
| `PasswordHasher`           | `Argon2PasswordHasher`                           | always                             |
| `TokenService`             | `JWTTokenService`                                | always                             |

The container is built once at import (`container.py:54`), stored on
`app.state.container`, and injected into route handlers via
`api/deps.py:get_container`. AI selection (`container.py:57`): if
`ai_provider` is `"mock"` → `MockAIProvider`; else if a Gemini API key exists →
`GeminiProvider`; otherwise it warns and falls back to the mock.

---

## 3. Authentication & Authorization Flow

**Register / Login** (`identity/api/routes.py`, `identity/application/service.py`):

1. Client `POST /api/v1/auth/register` with `{email, password, full_name?}`.
2. `IdentityService.register` checks the email isn't taken (`ConflictError` if so),
   hashes the password with **Argon2**, persists the `User`, and issues tokens.
3. `login` verifies the password and returns a `TokenResponse`.

**Token issuance** (`_issue_token` in `identity/application/service.py:61`):

- Access token: JWT (HS256), `role` claim, 30 min TTL (`access_token_expire_minutes`).
- Refresh token: JWT, `token_type="refresh"`, 30 day TTL.
- Both stored in `localStorage` by the frontend API client.

**Authorization on requests**:

- `identity/api/deps.py` (`CurrentUser`) decodes the Bearer token and loads the user.
- `api/deps.py:require_owned_video` verifies the video belongs to the caller before
  any transcript / analysis / clip / subtitles / stream route runs.
- Projects/videos check `project.owner_id == user.id` in the services.

**Refresh** (`/api/v1/auth/refresh`): decode refresh token, reload user, re-issue a
new access/refresh pair. The frontend auto-refreshes once on a 401
(`frontend/src/lib/api.ts:58`) and redirects to `/login` if refresh fails.

**Rate limiting** (`api/middleware/rate_limit.py`): Redis sliding-window limiter
wrapped as ASGI middleware over all API requests.

---

## 4. Project & Video Management

### 4.1 Projects

- `POST /api/v1/projects` → `VideoService.create_project` → new `Project` row (UUIDv7).
- `GET /api/v1/projects` → paginated list scoped to the owner.
- `DELETE /api/v1/projects/{id}` → cascade deletes videos/jobs/transcripts/analysis/clips.

### 4.2 Video Upload (signed-URL flow)

1. **Start** — `POST /api/v1/videos` (`videos/api/routes.py:132`)
   - Validates `content_type` starts with `video/`.
   - Creates a `Video` row with `status="uploading"`, `storage_key="videos/{video_id}/{filename}"`
     (UUIDv7 generated client-side in the service).
   - `LocalStorageProvider.signed_upload_url` returns an HMAC-signed, 1-hour URL:
     `GET/PUT /api/v1/storage/{key}?action=upload&expires=…&token=…`
     (`storage/local_storage.py:57`).
2. **Upload** — frontend does `PUT upload_url` with the raw file
   (`frontend/src/lib/api.ts:223`). The storage route (`api/routes/storage.py`)
   verifies the signature + expiry, enforces a 1 GiB ceiling, and writes bytes to disk.
3. **Complete** — `POST /api/v1/videos/{id}/complete`
   - Verifies status is `uploading` and the object exists in storage.
   - Flips video to `processing`, then **enqueues** the first pipeline task:
     `metadata_extraction` (`videos/application/service.py:113`).

### 4.3 YouTube Import

1. `POST /api/v1/videos/import` with a YouTube URL (`videos/infrastructure/youtube.py`).
2. `extract_youtube_id` validates the URL with a regex (supports watch/shorts/embed/live/youtu.be).
3. Creates a `Video` row with `status="importing"` and enqueues `youtube_import`.
4. The worker downloads with **yt-dlp** (best mp4, merged), probes it, computes SHA-256
   checksum, uploads it into storage, persists metadata, and then chains into `ai_analysis`.

---

## 5. Background Pipeline (Worker)

All actors live in `backend/src/clipforge/worker/tasks.py`. Each is a `dramatiq`
actor (Redis broker, `max_retries=3`) that wraps an `asyncio.run(...)` coroutine.
Success of one stage **enqueues the next** via `_enqueue(...)` (`tasks.py:341`).

Every stage runs through `JobTracker.begin/completed/failed` (`worker/tasks.py`)
which maintains a `Job` row per `(video_id, type)` with a dedupe key (unique
constraint, so restarts resume rather than duplicate work) and publishes status
events; a video can have at most 5 job attempts before being marked failed.

### Stage 1 — `metadata_extraction`

`MetadataExtractionService` (`processing/application/service.py`):

1. `begin(video_id, storage_key)`:
   - **Idempotency guard** via a `dedupe_key = f"{video_id}:metadata_extraction"` on the
     `jobs` table (`unique=True`). If an existing job is `running`/`succeeded`, skip.
   - Creates (or resumes) a `Job` with `type="metadata_extraction"`.
   - Publishes `{"status": "processing", "stage": "metadata_extraction"}`.
2. `extract(job)`:
   - `download_to_tempfile` streams the video from storage to a temp file and
     computes its SHA-256 + size.
   - `run_ffprobe` + `build_metadata` extracts format/duration, video stream
     (codec, width/height, fps, profile), and audio stream (codec, sample rate).
   - Persists `checksum`, `size_bytes`, `duration_seconds`, `metadata_json` onto the
     video, keeping status `processing`.
3. On success → job `succeeded`; on failure → job `failed`, video `failed`,
   status event published. Then enqueues **`ai_analysis`**.

### Stage 2 — `ai_analysis`

`AnalysisService` (`analysis/application/service.py:32`) runs four AI steps
concurrently and then persists everything:

1. Publishes `{"status": "analyzing", "stage": "ai_analysis", "message": "Starting AI analysis"}`.
2. Downloads the video to a temp file and builds a `VideoInput`
   (`storage_uri`, `mime_type`, `duration_seconds`).
3. `analyze_video(video_input)` → **understanding** (topic, summary, audience).
4. `generate_editing_plan(video_input, understanding)` → candidate clips
   (`start_time`, `end_time`, `hook`, `viral_score`, `emotion`, `category`,
   `thumbnail_text`). **Gemini** (`ai/gemini_provider.py`) uploads to the Gemini
   Files API, polls until `ACTIVE`, then calls `gemini-flash-latest` with forced JSON
   (`responseSchema`); **Mock** (`ai/mock_provider.py`) returns one deterministic clip.
   Each Gemini call tries a **API-key fallback chain** in order
   (`GEMINI_API_KEY`, then `GEMINI_API_KEYS`) — if one key fails, 401s, or its
   daily quota is exhausted, the next is used; the last-used key labels the
   usage rows.
5. `recommend_preset(video_input, editing_plan, understanding)` → picks a **preset**
   (`podcast` / `storytelling` / `gaming` / `tutorials` / `news_commentary` /
   `viral clips`) based on the analysis; unknown → `None` → clips render in
   **original** format.
6. `normalize(video, editing_plan, preset)` — enforces the preset's
   `target_duration` and clip count so the plan matches real constraints
   (Mock/Small-N videos previously produced nonsense "plan" numbers). Never
   exceeds video duration, never returns zero clips.
7. `transcribe(video_input)` → word + segment transcript
   (`language`, `segments`, flattened `words`).
8. Persists an `AnalysisResult` row with `understanding`, `editing_plan`,
   `recommended_preset`, `ai_model`; a `Transcript` row; publishes progress
   messages (analysis complete, preset recommendation).

On success → enqueues **`clip_extraction`**. On failure → status `failed` published.

### Stage 3 — `clip_extraction`

`ClipService` (`clips/application/service.py`):

1. Loads the video + its `AnalysisResult.editing_plan`.
2. `create_clips_from_editing_plan` creates one `Clip` row per candidate
   (`status="pending"`, title from hook, start/end/duration, keeps the raw candidate
   JSON in `editing_plan_json`). Timestamps are normalized via `clip_time(...)`
   (`common/times.py`) which accepts `"MM:SS"` or numeric seconds.
   Each clip's `format` is derived from the video's `recommended_preset`:
   `podcast` → `16:9`, `storytelling`/`gaming`/`tutorials`/`news_commentary` →
   `9:16`, `viral clips` → `original`. `default` preset (upload/import) → `original`.
3. Re-downloads the source video to a temp file, then **per clip**:
   - `mark_cutting` → `pending → cutting`.
   - `FFmpegCutter.cut_clip` runs `ffmpeg -ss <start> -i src -t <dur>` → H.264/AAC,
     `+faststart`, CRF 23 (`clips/infrastructure/ffmpeg_cutter.py`).
   - Uploads the cut MP4 into storage at `clips/{clip_id}/clip_{clip_id}.mp4`.
   - `FFmpegThumbnailGenerator` extracts a JPEG at the clip midpoint into
     `clips/{clip_id}/thumb_{clip_id}.jpg` (thumbnail failure is non-fatal).
   - `mark_ready` → `cutting → ready` with the storage keys set.
   - Any per-clip error → `mark_failed` (the loop continues with remaining clips).
4. Publishes `{"status": "rendering", "stage": "clip_extraction", "message": "N clips extracted, preparing renders"}`.
   The video **stays `processing`** — the render stage decides readiness.

### Stage 4 — `render`

`RenderingService` (`rendering/application/service.py`), runs once per clip:

1. `_render_clip(clip)` picks the output format from `clip.format`:
   - `16:9` → `1920×1080` landscape; `9:16` → `1080×1920` portrait;
   - `original` → identity (source dimensions, no resize/pad).
2. **Caption engines** — the `caption_engine` config picks how MotionCaption
   captions are burned (`worker/tasks.py` passes `settings.caption_engine`):
   - `frames` (default): `build_motion_caption_frames` (`lyrics/application/
     frames.py`) windows the transcript words to the clip, compiles them with
     the MotionCaption engine, and renders **RGBA PNGs** for the whole clip
     duration (`000000.png, 000001.png, …` at 30 fps) into the scratch dir;
     `CompositeRenderer._render_with_filter` feeds the sequence to ffmpeg's
     image2 demuxer and composites it with `overlay` — captions are pixels, so
     arbitrary animation works and only overlay events (emoji/CTA/lower-third)
     burn via libass.
   - `ass`: `build_motion_caption_ass` (`lyrics/application/ass.py`) exports
     the same timeline as an animated ASS document whose PlayRes matches the
     canvas, burned with the `ass` filter.
   - `legacy`: `build_caption_ass` (`rendering/domain/captions.py`) — the
     original word-by-word mobile ASS, retained as the fallback when an engine
     path has no words.
3. **Blueprint theming + karaoke emphasis** — the AI Director's
   `analysis.editing_blueprint.global_style.subtitle_theme` wins over the
   preset/editor style: `caption_theme_hint` maps `colors` → accent/muted/
   outline, `animation`/`word_animation` → a canonical animation strategy,
   `style_name` → a MotionCaption theme, and `highlight_words` become
   clip-local `emphasis_indices` (karaoke emphasis on the active word).
4. **Face-aware placement** — `detect_face_boxes` (`rendering/infrastructure/
   face_analyzer.py`) samples the clip at 2 fps through the *same* crop/scale
   chain the composite uses, runs the YuNet ONNX detector, scales the boxes to
   output-canvas pixels, and passes them as `CaptionRequest.faces` with
   `PlacementConfig(strategy="face-aware")` so captions glide off faces
   (gracefully skipped when OpenCV/model/decode is unavailable).
5. **Smart re-framing** (`rendering/domain/framing.py` + `framing_analyzer.py`):
   for portrait canvases, `RenderingService._framing_plan` derives the 9:16 crop
   window from the source aspect, samples the clip at 2 fps via an ffmpeg
   rawvideo pipe, and tracks the subject center — YuNet ONNX face detection
   (`/opt/opencv/face_detection_yunet.onnx`) with a motion center-of-mass
   fallback. `build_crop_expressions` emits piecewise smoothstep `crop` filter
   expressions (`crop=W:H:'x':'y'`, single-quoted because `if()` commas would
   otherwise split the filtergraph) so the window glides from keyframe to
   keyframe. Landscape canvases and untrackable sources keep the plain center
   crop.
6. `CompositeRenderer.render_clip` runs the full chain — crop/zoom, caption
   overlay (frames or ASS), overlay events, and audio (music bed + beat-timed
   SFX) — to `rendered_{clip.id}.mp4`, uploads it, and generates a thumbnail.
7. `mark_rendered` → clip `ready → rendered`, sets `render_storage_key` and the
   `rendered` flag, publishes `video.rendered` event (`"N clips rendered"`).
8. On success → `job.success` and, when **all** of the video's `ready` clips are
   rendered, flips the video to `ready` and publishes `{"status": "ready",
   "stage": "render"}`.

### Stage 5 — `dead_letter`

`dead_letter` marks the video `failed` with a human-readable message (e.g. no
clips produced) after the 5-attempt budget is exhausted, and publishes a
`failed` status event so the frontend stops waiting.

### Chain overview

```
[complete_upload]              [youtube_import]
        │ enqueue metadata            │ enqueue ai_analysis
        ▼                             ▼
metadata_extraction ──► ai_analysis ──► clip_extraction ──► render ──► video.status = ready
      (ffprobe)          (Gemini)          (FFmpeg cut)      (FFmpeg composite + captions)
```

`jobs` rows are written per stage with dedupe keys, and video status transitions:
`uploading → processing → analyzing → processing → ready` (or `failed` at any
point). YouTube adds an `importing → processing` leg. A clip's own lifecycle is
`pending → cutting → ready → rendered`.

---

## 6. Real-Time Status (Redis Pub/Sub + SSE)

- The worker publishes JSON events to the Redis channel **`clipforge:status`**
  via `RedisStatusNotifier.publish` (`processing/infrastructure/status.py`).
- `GET /api/v1/videos/{video_id}/stream` (`api/routes/status.py`) is a **Server-Sent
  Events** endpoint: after an ownership check it subscribes to the channel and yields
  only events whose `video_id` matches, emitting a `status` event per update and a
  `complete` event then closing when status is `ready` or `failed`.
- The frontend wraps this with `EventSource` (`frontend/src/lib/api.ts:345`) and
  renders the live stage/message in the project & video detail pages; on `complete`
  it reloads the data.

---

## 7. Delivery & Export (Read Paths)

All owned-object checks happen before returning data.

| Endpoint                                    | What it does                                                |
|---------------------------------------------|-------------------------------------------------------------|
| `GET /videos/{id}/transcript`               | Returns `Transcript` segments + words (JSON).               |
| `GET /videos/{id}/analysis`                 | Returns `AnalysisResult` (understanding + editing plan).    |
| `GET /videos/{id}/clips`                    | Paginated `Clip` list (each with `format`, `rendered`, download URLs). |
| `GET /videos/{id}/subtitles?format=srt|vtt` | Renders transcript to SRT/VTT text (`analysis/infrastructure/subtitles.py`). |
| `GET /clips/{id}/download`                  | Returns a fresh signed download URL for the clip MP4.       |
| `GET /projects/{id}/clips`                  | Paginated `Clip` list for a project.                        |
| `DELETE /clips/{id}`                        | Deletes a clip row (and its file on disk).                  |
| `GET /ai/usage`                             | Daily AI quota: per-key requests + tokens used/remaining (`usage/`). |

Downloads reuse the same HMAC-signed storage endpoint
(`GET /api/v1/storage/{key}?action=download&expires=…&token=…`) so video/clip files
can be streamed to the browser without an auth header.

### AI usage tracking

Every successful Gemini call reports its `usage_metadata` through a recorder
callback wired in `container.py`; rows land in the **ai_model_usage** table
(date, model, key_label, operation, prompt/response/total tokens, optional
video_id). `GET /api/v1/ai/usage` aggregates today's rows per API key against
the `GEMINI_DAILY_TOKEN_LIMIT` / `GEMINI_DAILY_REQUEST_LIMIT` quotas. The
dashboard header's `UsageBar` (`frontend/src/components/UsageBar.tsx`) polls it
every 30s and shows a token progress bar plus a per-key "requests / limit ·
left" count.

---

## 8. Frontend Pages

| Route                               | Purpose                                         | Key calls                                 |
|-------------------------------------|-------------------------------------------------|-------------------------------------------|
| `/login`, `/register`               | Auth via `ApiClient.login/register`             | stores JWT pair in localStorage            |
| `/dashboard`                        | Project CRUD list                               | `listProjects`, `createProject`, `deleteProject` |
| `/dashboard/[projectId]`            | Video list, upload, YouTube import, live status | `startUpload`→`uploadFile`→`completeUpload`, `subscribeStatus` |
| `/dashboard/[projectId]/[videoId]`  | Clip list, transcript, SRT/VTT download         | `listClips`, `getTranscript`, `getSubtitles`, `getClipDownloadUrl` |

The single `ApiClient` (`frontend/src/lib/api.ts`) handles tokens, automatic
refresh-on-401, and typed payloads for every endpoint above.

---

## 9. Data Model (key entities)

`db/models.py` — all PKs are UUIDv7; timestamps auto-set.

- **users** — email (unique), argon2 password_hash, role, is_active.
- **projects** — owner_id (FK, CASCADE), name, status.
- **videos** — project_id, filename, source_url (YouTube), storage_key (unique),
  checksum, content_type, size_bytes, duration_seconds, metadata_json (JSONB), status.
- **jobs** — video_id, type, status, attempts/max_attempts, dedupe_key (unique),
  last_error.
- **transcripts** — video_id (unique), language, segments (JSONB), words (JSONB).
- **analysis_results** — video_id (unique), understanding (JSONB), editing_plan
  (JSONB), ai_model, ai_cost_cents.
- **ai_model_usage** — date (indexed), model, key_label (indexed), operation
  (`analyze_video` / `transcribe` / `generate_editing_plan`), prompt_tokens,
  response_tokens, total_tokens, optional video_id (FK, SET NULL).
- **clips** — video_id + project_id, title, start/end/duration_seconds, storage_key,
  thumbnail_storage_key, format (`16:9`/`9:16`/`original`), render_storage_key,
  rendered (bool), editing_plan_json (JSONB), status.

Migrations are consolidated in `backend/alembic/`.

---

## 10. Configuration

`config.py` (pydantic-settings, `.env` overridable) — notable keys:

| Key                         | Default                                  | Purpose                     |
|-----------------------------|------------------------------------------|-----------------------------|
| `DATABASE_URL`              | `postgresql+asyncpg://clipforge@:5436`   | async SQLAlchemy engine     |
| `REDIS_URL`                 | `redis://localhost:6382/0`               | broker + pub/sub + limiter  |
| `JWT_SECRET` / token TTLs   | dev secret, 30m/30d                      | token signing               |
| `AI_PROVIDER`               | `gemini`                                 | `gemini`/`openai`/`mock`    |
| `GEMINI_API_KEY`            | (none)                                   | falls back to mock          |
| `GEMINI_MODEL`              | `gemini-flash-latest`                       | Gemini model to use        |
| `GEMINI_API_KEYS`           | (empty)                                  | comma/JSON list of fallback keys tried after `GEMINI_API_KEY` |
| `GEMINI_DAILY_TOKEN_LIMIT`  | `200000`                                 | daily token quota per model |
| `GEMINI_DAILY_REQUEST_LIMIT`| `20`                                     | daily request quota per model |
| `STORAGE_ROOT`              | `./storage`                              | local file store            |
| `STORAGE_SIGNING_SECRET`    | dev secret                               | signed URL HMAC             |
| `PUBLIC_BASE_URL`           | `http://localhost:8000`                  | signed URL host             |

---

## 11. Testing & Verification

```bash
cd backend && .venv/bin/pytest tests/ -v     # all tests (needs Docker services)
cd backend && .venv/bin/pytest tests/unit/ -v # unit only (no Docker)
cd backend && .venv/bin/pytest tests/api/ -v  # API integration (needs Docker)
```

- Unit: mock AI provider, clip service, analysis service, Gemini provider,
  identity service, video service, subtitles, pagination, YouTube URL validation.
- API: auth + projects integration tests.
- Dev smoke path: `make up` → `make migrate` → `make seed`
  (demo user `demo@clipforge.ai` / `demo1234`) → `make frontend-dev`,
  then upload a video or paste a YouTube URL and watch the SSE status update.

---

## 12. Known Boundaries / Next Steps

- **Storage**: local disk only; S3 provider port is stubbed conceptually but not
  implemented — signed URLs would need to become presigned S3 URLs.
- **Uploads**: single PUT with a 1 GiB ceiling; S3-style multipart/resumable is planned.
- **AI analysis**: the editing plan + transcript are separate Gemini calls against
  a freshly-uploaded file; file caching exists per-process only.
- **Rendering**: captions are motion-typography rendered by the MotionCaption
  engine — the default `frames` backend composites animated RGBA caption
  frames (font baked into the worker image) with ffmpeg; `ass` and the legacy
  word-by-word ASS stay switchable via `caption_engine`. The AI Director's
  blueprint themes captions (colors/animation/emphasis words, surfaced in the
  video detail page); face-aware placement steers captions off YuNet faces.
  Font uploads and a per-clip caption overlay editor remain future work. The
  `9:16` path smart-crops the subject (YuNet face tracking with a motion
  fallback, sampled at 2 fps); the analyzer does no multi-object selection,
  smoothing of dropped frames is minimal, and untrackable sources still
  center-crop.
- **Frontend**: basic, functional UI; the video detail page surfaces clip `format`
  and rendered output, but there is no caption overlay editor, timeline editor, or
  clip approval workflow yet.
