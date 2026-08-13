# ClipForge AI — Work Log & Current State

A running log of everything built so far, milestone by milestone. Each entry links
to the commit(s) that landed it. For the how-it-works detail see
[`flow.md`](./flow.md); for the editing-style feature design see
[`editing-plan-ai-fields.md`](./editing-plan-ai-fields.md).

> Current HEAD: **M4 complete** — the lyrics-first wiring milestone shipped in
> four commits: face-aware placement (M4a), blueprint-driven caption theming +
> karaoke emphasis (M4b), the frontend caption-theme surface (M4c), and this
> docs refresh. Captions are MotionCaption-rendered (`frames` engine by
> default), steer around faces, and take their look/emphasis from the AI
> Director's blueprint. See sections 13-16 below; earlier milestones were
> committed to `origin/main`.

---

## 1. Foundation (2026-08-04)

- Monorepo scaffold: `backend/`, `infra/`, root `Makefile`
  (`3848a7c`, `866f44e`).
- Pydantic-settings config, structured logging, error taxonomy
  (`172721e`).
- Core DB models, async SQLAlchemy session, first Alembic migration
  (`b3272f3`).
- Provider port interfaces — AI, storage, queue, cache (`4533f59`).
- Concrete providers: local storage, Dramatiq, Redis cache, Gemini/mock AI
  (`9a8556c`).
- DI container, FastAPI app, health checks (`65023b5`).

## 2. Identity & Video Pipeline (2026-08-04)

- Identity bounded context: register / login / me, JWT + Argon2 (`4481665`).
- Video processing pipeline: analysis, clips, subtitles, worker services
  (`44bb723`).
- High-priority fixes + pagination/deletion (`bb5428f`).
- Thumbnail generation, SRT/VTT export, seed script, consolidated migrations
  (`43f987c`).
- Refresh tokens + Redis sliding-window rate limiting (`beeedfe`).
- Next.js frontend for testing (`e20afe6`); Makefile venv-path fixes
  (`845b0e0`).
- 48 tests (unit + API integration) + comprehensive README (`38726d2`).

## 3. AI Director & Event-Driven Pipeline (2026-08-05)

- YouTube import + Gemini Files API integration; pipeline status fixes
  (`662353a`).
- Event-driven foundation: durable events, idempotent jobs (dedupe keys),
  dead-letter queue, observability, admin API (`00cf9ad`).
- **AI Director**: real video understanding, editing-plan normalization,
  preset recommendation (`81b9998`).
- **Caption rendering engine**: libass ASS burn-in, render pipeline stage,
  `video.rendered` event (`d6df180`).

## 4. Editing Engine v2 — presets, re-framing, quota (2026-08-05 → 08-06)

- Preset-aware clip formats (`16:9` / `9:16` / `original`), format-aware
  caption rendering, `flow.md` refresh (`212b88b`).
- **Smart 9:16 re-framing**: YuNet face detection + motion-tracking crop,
  mock transcript words, `AI_PROVIDER` override (`9e884fd`).
- Gemini API key + model as single env-backed config (`65119ca`).
- AI usage quota bar — per-model tokens + requests, multi-model Gemini
  fallback (`bd3b738`).
- Gemini API-key fallback chain (own Files upload per key) + per-key usage
  bar (`7b7fe40`).
- Switch to `gemini-flash-latest` (`6e4f83c`).
- `render_storage_key` + captions fix + Shorts-style framing (`547c117`).
- **Editing Engine v2**: style presets & rendering engines (`29e7533`).
- AI model fallback chain (`3fafcda`).

## 5. Beat-Aware Composite Rendering (2026-08-07)

- Stable processing status streaming: dedup SSE, monotonic progress bar
  (`685fd7a`).
- **Beat-aware composite rendering** (`f6319ab`):
  - Audio beat detection drives punch-in **zoom keyframes** (comma-free
    Gaussian `exp()` pulses in ffmpeg filter expressions — `if()` commas
    would split the filtergraph).
  - Word-by-word **karaoke captions** burned in via ASS.
  - **Music bed** (volume ducked under vocals) + **SFX** layers.
  - `ffmpeg filter option values can NEVER contain commas`.

## 6. User-Driven Editing Style (2026-08-07) — `b09ff53`

The most recent feature; fully verified end-to-end against real Gemini.

- `videos.editing_style` column (migration `c1e2d3e4f5a6`, applied) —
  captured from a free-text box on upload ("caption style, transitions,
  SFX, zoom, emoji, CTA, …").
- `generate_editing_plan(video, preset, context, editing_style)` now returns:
  - plan-level `EditorStyle` (`caption_style`, `caption_colors`,
    `transition_style`, `sfx_enabled`, `sfx_types`, `music_mood`,
    `music_volume_db`, `emojis_enabled`, `punch_zooms`, `zoom_intensity`,
    `cta_enabled`, `cta_text`);
  - per-clip `emphasis_times`, `emoji_triggers`, `cta_text`, `hook_text`.
- Applied at render time in `apply_style_overrides`: caption accent color +
  animation, punch zooms from `zoom_intensity`, transition type, SFX/music
  overrides; emoji + CTA burned in as ASS events; `hook_text` feeds the
  lower third.
- Normalizer sanitizes `emphasis_times` (clip-local, in-window, deduped,
  sorted, max 8) and `emoji_triggers` in both rebuild passes.
- API: `CreateVideoRequest.editing_style`; frontend: textarea on the project
  page, `api.startUpload(..., editingStyle)`.
- New unit tests (`test_normalizer.py`, extended `test_rendering_service.py`).

### Live verification summary

- Test video `019fd8d4-64b8-7bc0-94bb-87bd128a983c` (project
  `019fd8d4-3296-776c-aa66-3d7a3183a253`), style prompt: "Fast-paced meme
  editing: karaoke captions in yellow, punch zooms, 🔥 emoji, Subscribe CTA,
  upbeat music, whoosh SFX".
- 4/4 clips rendered. Plan `style` populated (karaoke, FFFF00/FFFFFF,
  punch_zooms, zoom_intensity 0.3, CTA "Subscribe", whoosh SFX, upbeat music,
  -3 dB, cut transitions).
- Every clip has `hook_text`/`emphasis_times`/`emoji_triggers`; e.g. clip
  `019fd8d6-aa85-70b3-a868-ffe02c2c52ba`: emphasis [2.0, 12.0], 🔥 at 2.0 s,
  hook "When you meet HIM at Holi 🔥".
- Reconstructed ASS: emoji dialogue 2.0–4.0 s, CTA "Subscribe" 20.0–25.0 s,
  accent FFFF00, zoom keyframes (0.5, 1.14)/(2.0, 1.11)/(12.0, 1.11).
- Rendered frame confirmed 233 yellow caption pixels; output valid h264
  1920×1080, 25 s, ~13 MB.

### Known caveats from verification

- `hook_text` only displays when the preset enables lower thirds
  (`lower_thirds_enabled`).
- The worker container has **no color-emoji font** (fc-list: 271 fonts) so
  emoji burn in monochrome. Fix = install a color-emoji font in the image.
- `transition_style` other than cut/none is recorded but not yet rendered
  (the `TransitionEngine` is a documented non-goal for M6).
- `clips` API does not expose `editing_plan_json`; check per-clip fields in
  Postgres: `docker exec clipforge-postgres-1 psql -U clipforge -d clipforge
  -t -c "SELECT editing_plan_json FROM clips WHERE id='…';"`.

---

## 7. Artifact Intelligence Pipeline + Workflow Engine (2026-08-07) — M1 (`1b9e838`)

First milestone of the horizontal-scale platform direction: a **centralized,
crash-resumable workflow engine** drives **artifact-producing intelligence
workers** (metadata / scene / motion / beat), fully live-verified against the
real stack. The legacy pipeline is untouched and runs side-by-side.

- **Artifact store** (`clipforge/artifacts/`): versioned JSON artifacts written
  to storage (`artifacts/{video_id}/{kind}.json`, envelope `schema_version=1`:
  `{schema_version, kind, version, video_id, created_at, payload}`) with a
  Postgres index row (checksum, size) for cache lookups.
- **Workflow engine** (`clipforge/workflow/`): a persisted DAG per video
  (`workflow_nodes` table) with statuses `waiting → running → succeeded |
  failed | skipped`. Retries are owned by the **engine** (attempts budget
  `intelligence_max_attempts=5`, exponential backoff base 1000 ms, cap 60 s),
  not by dramatiq (`intelligence_worker` runs with `max_retries=0`).
  `reconcile(stale_seconds=600)` recovers nodes crashed mid-run.
- **Workers** (`clipforge/intelligence/workers/`): `metadata` (ffprobe +
  thumbnail), `scene` (PySceneDetect content detector, threshold 27.0, with
  single-scene fallback), `motion` (OpenCV Farneback flow sampled at 2 fps,
  640-wide — CPU cost proportional to duration, not framerate), `beat`
  (energy engine reusing `audio_analysis.py`; optional `librosa` engine).
- **DAG**: `metadata` → `scene`/`motion`/`beat` (depend on metadata). All on
  the dedicated `media` queue so the intelligence workers can be scaled
  independently. Actors: `start_intelligence`, `intelligence_worker`,
  `workflow_reconcile`.
- **Cache**: an artifact for the same worker `version` + existing blob ⇒
  `CACHED` (node `skipped`, nothing recomputed); a worker `version` bump
  invalidates and recomputes.
- **API**: `POST /api/v1/videos/{video_id}/intelligence/start` → 202
  `{"status": "started"}` (idempotent: engine only creates missing nodes).
- **DB**: migration `0d71ad8720ad` (applied) adds `artifacts` +
  `workflow_nodes` (unique `(video_id, kind)`, FK cascade, indexes).
- **Config**: `queue_media` ("media"), `beat_detector` ("energy" | "librosa"),
  `intelligence_max_attempts` (5).
- **Resilience**: missing optional deps degrade gracefully — SceneWorker falls
  back to a single scene when PySceneDetect is unavailable (pyscenedetect is
  **not installable in this environment**, so scene runs in fallback mode);
  BeatWorker's energy engine needs no ML deps.
- **Observability**: `clipforge_worker_duration_seconds`,
  `_worker_processing_duration_seconds`, `_worker_queue_time_seconds`,
  `_worker_failures_total` via `record_worker_completion(...)`.
- 35 new unit tests (artifacts, workflow engine, real workflow repo on sqlite,
  intelligence service cache, media workers against real ffmpeg fixtures,
  beat workers, video-service enqueue). Fixed a pre-existing broken sqlite
  `session` fixture (`DeclarativeBase.metadata` → `Base.metadata`) and made
  `JSONB` portable (`JSON` with `JSONB` variant on Postgres) so the ORM models
  compile on SQLite.
- **Notable bugs found & fixed while verifying live**: (1) `start_intelligence`
  was enqueued to the `default` queue while the actor declared `media` — now
  routed via the `queue_media` setting; (2) `MissingGreenlet` crash on
  expression-based `attempts + 1` flush (async refresh added in
  `SQLAlchemyWorkflowNodeRepository._update`); (3) `retry()` reset nodes to
  `waiting` which the actor skips — it now re-claims (`mark_running`) before
  re-enqueue.

### Live verification summary

- `POST /api/v1/videos/{video_id}/intelligence/start` on test video
  `019fd8d4-64b8-7bc0-94bb-87bd128a983c` → 202; all four nodes reached
  `SUCCEEDED` (motion ~36 s on the 161 s source).
- Artifacts persisted with real payloads: metadata (161.12 s, h264,
  1440×1080), scene (`fallback_single_scene`, 1 scene), motion (`has_motion:
  true`, 322 intervals @ 2 fps), beat (energy, `has_audio: true`, 9 peaks).
- Idempotency: re-triggering start produced no duplicate nodes/artifacts and
  left all nodes final.

### Known caveats

- Scene detection currently runs in **fallback mode** everywhere because
  `pyscenedetect` cannot be installed here (mirror/firewall); install it where
  it's available to get real shot boundaries. Deps moved to the optional
  `intelligence` extra so the base image still builds.
- `librosa` is installed in the worker container at runtime (ephemeral — lost
  on recreate); the default `energy` engine does not need it.
- Workers download the source video to a temp file on each run; a long-term
  optimization is a sidecar cached decode.

## 8. Timeline Engine + Artifact-Driven Rendering (2026-08-07) — M2 (`a1bf07f`)

Second milestone: the **Timeline Engine** — the original motivation for M1.
A pure domain engine consumes the scene/motion/beat artifacts and emits a
`timeline` artifact (shot emphasis, punch-in zooms, cut timing), and the render
path now drives emphasis zooms/SFX from that artifact.

- **Timeline engine** (`clipforge/timeline/domain/engine.py`) — a pure,
  deterministic function of the three M1 payloads:
  - `shots`: per-shot `motion_score` (mean Farneback intensity normalized by
    the video max) and `beat_score` (beat density, capped at 3 beats) combined
    into `emphasis_score` (0.45 motion + 0.55 beat, clipped 0..1).
  - `punch_ins`: beat peaks inside an emphasized shot (`emphasis_score >=
    0.35`) plus motion **local maxima** above 60% of max intensity; candidates
    within 0.4 s are deduped (keep the strongest), then greedily spread with a
    minimum 0.6 s gap up to `MAX_PUNCH_INS = 10`.
  - `cut_points`: scene end times (excluding final duration) for downstream
    auto-cutting.
  - Graceful under missing artifacts (whole-video single shot, zero scores).
- **`timeline` worker** (`clipforge/intelligence/workers/timeline.py`,
  `timeline-v1`, inputs `scene`/`motion`/`beat`) — registered as the 4th leaf
  node in `WORKFLOW_GRAPH` and in `build_workers`. Declares `needs_source =
  False`, a new base contract flag (`IntelligenceWorker.needs_source`) so the
  pipeline **skips the source download** for pure-artifact nodes.
- **Render wiring** (`RenderingService`): the render task now injects
  `ArtifactRepository` + `ArtifactStore`; `_timeline_punch_ins()` reads the
  timeline artifact and `_render_clip` merges source-time punch-ins
  (converted to clip-local seconds, in-window) into the clip's emphasis
  timeline alongside AI `emphasis_times` and legacy beats — so emphasis zooms
  and SFX are now **artifact-driven end-to-end**, falling back to legacy
  beats when no timeline artifact exists.
- **API**: `GET /api/v1/videos/{video_id}/timeline` (owner-guarded, 404 when
  not yet computed) with a typed `TimelineResponse` schema, registered under
  the new `clipforge/timeline/` bounded context (`domain` engine,
  `application` service, `api` routes/schemas).
- 20 new unit tests: engine determinism/edge cases, worker contract, the
  `needs_source` skip-download path in `IntelligenceService`, and the render
  punch-in merge (with legacy-beat fallback).

### Live verification summary

- Worker restarted to load the new registry; re-triggering
  `intelligence/start` created **only** the missing `timeline` node and ran
  it (metadata/scene/motion/beat all cached → skipped). No source download
  for the timeline node.
- `GET /api/v1/videos/019fd8d4-…/timeline` returns: duration 161.12 s,
  `has_motion`/`has_audio` true, single fallback scene (pyscenedetect still
  unavailable), 8 punch-ins (6 beat + 2 motion, strengths 0.649–1.0, spread
  ≥0.6 s), `cut_points` empty (single scene).
- Full live re-render via `RenderingService` (bypassing the job-dedupe that
  skips already-handled render jobs): 4/4 clips rendered with per-clip
  artifact-driven SFX counts 8/4/2/4 (the punch-ins falling inside each clip
  window), music + captions + thumbnails all regenerated.

### Known caveats

- Scene detection still runs in fallback mode (pyscenedetect uninstallable
  here), so `cut_points` is empty on this video — real cut timing awaits real
  shot boundaries.
- `punch_ins[].strength` is emitted and served but not yet used to vary zoom
  scale/SFX volume at render time (times drive the emphasis zoom); strength is
  ready for a future variable-intensity pass.

---

## 9. Upload → Store → Prompt → Process (2026-08-07) — M3 (`50e3b38`)

Changed the product flow: uploading a video **only stores it**; nothing is
processed until the user attaches an optional per-video prompt and clicks
**Process**.

- `VideoStatus.UPLOADED` (`uploaded`); `complete_upload` now transitions
  `uploading → uploaded` and **no longer enqueues `metadata_extraction`** —
  an upload sits idle in storage.
- **Per-video prompt** = the existing `videos.editing_style` column, moved off
  the upload step (`CreateVideoRequest` no longer carries it). New
  `PATCH /api/v1/videos/{video_id}` (`UpdateVideoRequest.editing_style`) to
  set/clear it per video; `VideoResponse.editing_style` now returned everywhere.
- **`POST /api/v1/videos/{video_id}/process`** — kicks off the full pipeline on
  demand: `metadata_extraction` (→ AI analysis → clip extraction → render) **and**
  `start_intelligence` (the M1/M2 artifact workflow), and sets status
  `processing`. Guarded (rejects `uploading/importing/processing/analyzing` and
  missing storage objects); new `update_editing_style` repo method.
- **YouTube imports** made consistent: `youtube_import` lands in `uploaded`
  (no auto-enqueued `ai_analysis`) — imported videos also wait for Process.
- Frontend: removed the pre-upload "editing style" textarea; each video row on
  the project page (and the video detail page) now has an inline prompt input +
  green **Process** button (shown for `uploaded`/`failed`); upload flow ends at
  "Stored" with no auto-streaming. `api.updateVideoStyle` + `api.processVideo`.
- 6 new unit tests (`complete_upload` stores without jobs, `process_video`
  enqueues both pipelines, active-state rejection, prompt set/clear).

### Live verification summary (fresh upload `019fdccf-8192-704c-8762-01fec469cd21`)

- Uploaded `video.mp4` → `complete` → status `uploaded`, **zero jobs** enqueued.
- `PATCH` set prompt "Fast-paced meme editing… Subscribe CTA" → still `uploaded`.
- `POST /process` → status `processing`; `metadata_extraction` job + all 5
  workflow nodes created.
- Full pipeline finished: **4/4 clips ready**, all 4 legacy jobs succeeded.
- `beat`/`timeline` completed and `GET /timeline` returned the live artifact
  (161.12 s, 8 punch-ins: 6 beat @20.25–110.25 + motion @113.0/148.48).

### Known caveats

- **Pre-existing worker flake (not from this change):** under concurrent load
  the shared SQLAlchemy async engine can crash a dramatiq thread with
  *"`Lock is bound to a different event loop`"* (engine `_exec_once_mutex` is
  loop-bound). `NullPool` already avoids pooled-connection reuse; the failure
  killed the first `beat` message here (node stuck `RUNNING`), recovered by
  re-enqueueing `intelligence_worker` for that node. A `workflow_reconcile`
  scheduler would self-heal this automatically.
- Re-processing a `ready` video with a new prompt is not yet supported (job
  dedupe would skip everything); Process is offered for `uploaded`/`failed`.

---

## System Design Concepts Used

### Architecture style
- **Hexagonal / Ports & Adapters** — all infrastructure behind protocol
  interfaces in `common/ports/` (`AIProvider`, `StorageProvider`,
  `QueueBroker`, `CacheProvider`, `EventBus`, `PasswordHasher`,
  `TokenService`); concrete providers are swapped at wiring time.
- **Dependency Injection** — a single `Container` built once at import
  (`container.py`), held on `app.state.container`, injected into routes via
  `api/deps.py`.
- **Modular monolith / bounded contexts (tactical DDD)** — `identity`,
  `videos`, `clips`, `analysis`, `rendering`, `processing`, `usage`, `admin`,
  each split into `domain / application / infrastructure` layers plus API
  routes; `Repository` pattern for persistence.
- **CQRS-ish read/write split** — write path is the background pipeline
  (services mutate state, publish events); read path is lightweight query
  endpoints + signed-URL streaming + SSE.
- **Strategy pattern** — style presets & rendering engines selectable per
  video (Editing Engine v2); `apply_style_overrides` layers AI style over the
  preset at render time.

### Messaging & pipeline
- **Queue-based decoupling** — the API enqueues and a Dramatiq worker
  (Redis broker) consumes; each stage *enqueues the next*, forming a
  chain (saga-orchestration-lite: metadata → AI analysis → clip extraction →
  render → dead-letter).
- **Event-driven status** — worker publishes status events; **durable event
  log** (`EventBus` over Redis Streams) supports publish + tail/replay for
  auditing and debugging (best-effort, never fatal to the pipeline).
- **At-least-once delivery with idempotency** — `jobs.dedupe_key` unique
  constraint means restarts resume instead of duplicating work.
- **Retry budget + dead-letter queue** — max 5 attempts per video; exhaustion
  lands in the `dead_letter` stage, which marks the video failed with a
  human-readable reason.
- **State machines** — video `uploading → processing → analyzing → processing
  → ready | failed`; clip `pending → cutting → ready → rendered`.
- **SSE over polling** — Redis Pub/Sub → SSE endpoint (`?token=` auth because
  EventSource can't send headers), deduped, terminates on `ready`/`failed`.
- **Centralized workflow engine (M1)** — a persisted DAG (`workflow_nodes`)
  orchestrates artifact workers; the engine, not the message bus, owns retries
  (attempts budget + backoff + crash-recovery reconcile). Enqueueing is
  lock-protected in the DB (stale-running guards) so at-least-once delivery can
  never double-run a node.
- **Artifact-cache pattern (M1)** — heavy analysis results are versioned
  artifacts (JSON blobs in storage + Postgres index); a cache hit = matching
  worker `version` + existing blob, so re-runs skip recomputation and the
  `metadata`→`scene/motion/beat` fan-out is idempotent.
- **Dedicated worker pool queue (M1)** — a separate `media` queue lets the
  intelligence workers scale independently of the legacy pipeline; routing is
  config-driven (`queue_media`).

### Storage & data
- **Download-to-temp → process → upload-to-storage** pipeline with SHA-256
  checksums captured at metadata/import time for integrity.
- **Signed (HMAC) URLs** with expiry for both upload (PUT, 1 GiB ceiling) and
  download — the storage endpoint needs no auth header.
- **UUIDv7** primary keys (time-ordered); **JSONB** for flexible payloads
  (metadata, editing_plan, transcript); consolidated Alembic migrations; FK
  cascade on project delete.
- **Redis sliding-window rate limiting** as ASGI middleware over all routes.

### AI integration
- **Failover / fallback chains** — multi-model Gemini fallback, per-key
  API-key chain (own Files upload per key; 401/quota → next key), and
  graceful degradation to MockAIProvider when no key is configured.
- **Structured LLM output** — forced JSON via Gemini `responseSchema`; a
  **normalization adapter** then enforces invariants (preset duration/clip
  count, in-window clip-local times, dedupe/sort, emoji sanitation) so AI
  output can never violate domain rules.
- **Quota metering** — per-model daily token/request quotas recorded through a
  callback; usage/`admin` endpoints + per-key dashboard usage bar.

### API & auth
- **REST + SSE**, signed-URL file flow (start → PUT → complete), ownership
  checks on every route (`require_owned_video`, cascade scoped to owner).
- **JWT access (30 min) + refresh (30 days)** with automatic refresh-on-401
  in the frontend client; **Argon2** password hashing.

### Operational qualities
- **Observability** — structured logging, admin API, job/event tracking,
  AI usage telemetry.
- **Async I/O** — asyncio throughout; every dramatiq actor wraps
  `asyncio.run(...)`; the EventBus is safe across the API and worker asyncio
  loops.

---

## 10. AI Video Director — Contract & Pipeline (2026-08-07) — M4 (uncommitted)

ClipForge is becoming an **AI Video Director**: the AI no longer hands back a
list of clips — it edits. The director watches the whole video and returns one
typed `EditingBlueprint` (global style + clips + a per-track timeline of
events, each with `timestamp` / `duration` / `parameters` / `reason`). The
renderer (M5) will execute these events deterministically; it never makes
creative decisions.

- **`directing/` module** — new bounded context:
  - `domain/blueprint.py`: typed models — `Track` enum (camera / subtitle /
    transition / overlay / emoji / music / effects / cta), `GlobalStyle`
    (color grading, subtitle theme, music), `BlueprintClip` (hook, story_role,
    viral/retention scores), `TimelineEvent`, `EditTimeline`, `EditingBlueprint`
    (schema_version 1). Event timestamps are in **source-video seconds**;
    per-clip renders apply only in-window events.
  - `domain/prompt.py`: `DIRECTOR_SYSTEM_PROMPT` (the provided spec, verbatim)
    + a JSON-schema appendix describing every track's allowed event types and
    parameter ranges.
  - `application/normalizer.py`: deterministic safety pass — clip windowing
    (20–45 s, 1 s overlap guard, short-clip extension), event repair (track
    aliases, per-track type whitelists, in-range timestamps, per-track caps,
    stable sort), global-style sanitization (hex colors, enum whitelists,
    clamped ranges). Empty tracks stay empty — it never invents decisions.
  - `application/service.py`: `DirectorService.direct()` and
    `legacy_plan_from_blueprint()` — projects the blueprint onto the old
    `editing_plan` JSON so clip extraction + the legacy composite renderer keep
    working unchanged.
- **`AIProvider.direct(...) -> EditingBlueprint`** — new abstract port method;
  implemented in `GeminiProvider` (director prompt + JSON response schema) and
  `MockAIProvider` (deterministic podcast blueprint).
- **Persistence** — `analysis_results.editing_blueprint` JSONB column
  (migration `d3e4f5a6b7c8`); `AnalysisResultRecord` + repo + API response
  expose it alongside the legacy `editing_plan`.
- **`AnalysisService.run_analysis` rewired** — `ai.direct` → recommend preset →
  `normalize_blueprint` → `legacy_plan_from_blueprint` → persist both; the
  `direct` operation is recorded in AI usage telemetry.
- **Live-verified** on `video.mp4` (161 s): real Gemini call returned a
  `storytelling` blueprint — 4 clips with story roles + scores, a warm
  cinematic grade, subtitle theme + highlight words, music (128 bpm, -6 dB),
  and 7 timeline events across camera/transition/emoji/effects, each justified
  by a reason. Fixed a live-only bug: Gemini Developer API rejects pydantic's
  `additionalProperties` (emitted for `dict` fields) — `_schema_for_gemini`
  strips it recursively.
- **Tests**: 13 new unit tests (blueprint validation, normalizer edge cases,
  legacy-plan projection, mock `direct`, schema stripping). 178 passed /
  2 skipped; ruff + mypy at baseline (3 pre-existing E501s, 53 pre-existing
  mypy errors); tsc clean.

---

## 11. MotionCaption lyrics integration — M1 (foundation)

ClipForge now embeds **MotionCaption** (`motion-caption>=0.1.2`, on PyPI) as
the motion-typography engine for caption/lyrics generation. ClipForge keeps
clip extraction, re-framing, zoom, music/SFX and delivery; MotionCaption owns
the compiled caption timeline. Caption backends (`legacy` ASS sweep /
MotionCaption ASS / MotionCaption frame overlay) are switchable via the new
`caption_engine` setting; only the legacy path is wired today — the MotionCaption
backends land in M2/M3.

- **New `lyrics/` bounded context** (`backend/src/clipforge/lyrics/`), clean
  architecture:
  - `domain/entities.py` — `LyricWord`, `LyricsRequest` (clip-local words,
    canvas, fps, preset, theme, accent/muted colors, animation, karaoke,
    emphasis indices, platform/safe-area), `CompiledLyrics` (wraps the
    canonical `SubtitleTimeline` + scalars).
  - `domain/ports.py` — `LyricsCompiler` port (`compile(request)`).
  - `application/theme.py` — preset → MotionCaption theme mapping
    (`podcast→clean`, `storytelling→cinematic`, `mrbeast→sport`, …), animation
    label aliases (`sweep/word-by-word/typewriter→karaoke`, `highlight→glow`,
    `glitch→bounce`), accent-hex normalization.
  - `application/service.py` — `LyricsService` facade (validation + port
    delegation).
  - `infrastructure/motion_caption.py` — `MotionCaptionLyricsCompiler`: builds
    the `CaptionRequest` (theme overrides for muted/accent colors, karaoke
    emphasis via `AIContribution`, platform/safe-area, `CompileOptions`
    animation strategy) and compiles deterministically (compiler LRU keyed by
    serialized request).
- **Config**: `caption_engine: "legacy" | "ass" | "frames"` (default `frames`,
  inert until the render backends land in M2/M3).
- **Tests**: 21 new unit tests (theme/animation/color mapping, compile
  determinism, karaoke emphasis, safe-area placement, empty/invalid requests).
  199 passed / 2 skipped; ruff clean except the 3 pre-existing E501s; mypy
  clean on the lyrics module and full repo at baseline.

---

## 12. MotionCaption ASS caption backend — M2 (uncommitted)

Second MotionCaption milestone: the **MotionCaption ASS engine is now wired
into the composite renderer**. When `caption_engine=ass`, captions are compiled
through the `lyrics` context and exported by MotionCaption's `AssExporter`
(animated `\pos` / `\fscx`/`\fscy` / `\c` / `\alpha` / `\t` chains per word) and
burned in with the existing `ass=` filter. The legacy word-by-word sweep
(`build_caption_ass`) stays untouched as the fallback, and `frames` remains the
not-yet-implemented end state (falls back to legacy with a one-time warning).

- **`lyrics/application/ass.py`** — the ASS backend:
  - `window_words(words, clip_start, clip_end)`: transcript words that fall
    inside the clip window, rebased to clip-local seconds (mirrors the legacy
    windowing so both backends agree on a clip's words).
  - `build_motion_caption_ass(...)`: builds a `LyricsRequest` (windowed words,
    canvas, preset → theme, accent/muted colors + animation from `RenderStyle`,
    karaoke) → `LyricsService.compile_lyrics` → `AssExporter.export(...)`
    (PlayResX/Y = output canvas, so libass burns text undistorted). Returns
    `None` when no words fall in the window so callers fall back to the legacy
    empty caption track.
- **`CompositeRenderer.render_clip`** gained `caption_ass: str | None = None`:
  a prebuilt MotionCaption ASS wins; otherwise it falls back to
  `build_caption_ass`. Overlay events (emoji / CTA / lower-third) are still
  appended on top in both cases.
- **`RenderingService`** resolves the engine: `caption_engine=ass` →
  `build_motion_caption_ass` (accent `style.caption.active_color`, muted
  `style.caption.muted_color`, animation `style.caption.animation`); `frames` →
  one-time warning + legacy fallback until M3; anything else → legacy. The
  worker passes `settings.caption_engine` through (`caption_engine` default
  stays `frames`).
- **Tests**: 12 new unit tests (`test_ass_engine.py`) — windowing
  (clip-local rebasing, partial-word clipping, empty-text, empty window), ASS
  output (PlayRes matches canvas, in-window words present / out-of-window
  absent, clip-local timings, accent/muted colors, preset theme, determinism,
  landscape canvas). 211 passed / 2 skipped; ruff clean except the 3
  pre-existing E501s; full-repo mypy at the same baseline as HEAD.

---

## 13. MotionCaption frame-based caption engine — M3 (uncommitted)

Third MotionCaption milestone and the **primary end state**: captions are no
longer limited to libass features. The typography is rendered by MotionCaption
as an **RGBA PNG sequence** (one frame per clip-local time step at the caption
fps, transparent everywhere except the text) and composited over the video
chain with ffmpeg's `overlay` filter. The legacy ASS sweep and the M2
MotionCaption-ASS path both remain switchable via `caption_engine`; the default
`frames` now actually renders.

- **`lyrics/application/build.py`** — shared request building for both
  backends: `window_words(...)` (moved here from the ASS module) and
  `clip_caption_request(...)` — a clip-local `LyricsRequest` from transcript
  words + render style (preset→theme, accent/muted colors, animation,
  karaoke). Returns None when no words fall in the clip window.
- **`lyrics/application/frames.py`** — `build_motion_caption_frames(...)`:
  compiles the request and writes `000000.png, 000001.png, …` into `out_dir`
  for the **whole clip duration** (`start=0, end=clip_end-clip_start`), not
  just until the last word. Returns None when the window is empty.
- **`CompositeRenderer`** — `render_clip` gained `caption_frames_dir` +
  `caption_fps`; `_render_with_filter` adds a second ffmpeg input via the
  **image2 demuxer** (`-framerate`, `-start_number 0`, `%06d.png`) and an
  `overlay=0:0:shortest=1:format=auto` after the crop/zoom/`ass` chain
  (`[base][caps]overlay…[v]`). Frame captions are pixels, so no word ASS is
  burned; overlay events (emoji/CTA/lower-third) still burn via libass using a
  new minimal `ass_header(canvas)` helper in `captions.py`.
- **`RenderingService`** — `_build_captions(...)` resolves the engine:
  `frames` → `build_motion_caption_frames` into the per-render scratch dir
  (cleaned up with it), `ass` → M2 exporter, else legacy. `caption_fps` = 30
  (`CAPTION_RENDER_FPS`).
- **Tests**: 8 new tests — frames engine unit tests (empty window → None,
  numbered PNG count = `floor(duration*fps)+1` covering the full clip,
  RGBA + opaque text pixels, determinism) + a **real-ffmpeg** render of the
  `static_video` fixture asserting the output is valid 320×240 and the caption
  frame composited (output frame ≠ source frame) + an overlay-only-ASS wiring
  test + a `RenderingService` frames-engine test. 219 passed / 2 skipped; ruff
  clean except the 3 pre-existing E501s; full-repo mypy at baseline.

---

## 14. MotionCaption face-aware caption placement — M4a

First piece of the M4 lyrics-first wiring: captions now steer around faces.
Faces are detected with the same optional OpenCV YuNet detector family as the
framing analyzer, boxes are mapped into **output-canvas pixels**, and the
MotionCaption placement engine moves each caption off them (vertical moves
preferred, with a configurable margin). Any failure — missing OpenCV, missing
model file, decode error — degrades to empty face boxes and the default
placement, so caption rendering never breaks.

- **`lyrics/domain/entities.py`** — `LyricsRequest` gained
  `faces: tuple[(left, top, right, bottom), ...]` (canvas px) and
  `face_margin: float = 16.0`.
- **`lyrics/infrastructure/motion_caption.py`** — the compiler maps each face
  to `CaptionRequest.faces` (`Face(box=Box(left, top, right, bottom))`) and,
  when any face is present, sets
  `CompileOptions(placement=PlacementConfig(strategy="face-aware",
  face_margin=...))`. Without faces the default placement is untouched.
- **`rendering/infrastructure/face_analyzer.py`** (new) —
  `detect_face_boxes(source_path, canvas, framing=None)` samples the clip at
  2 fps through the **same crop/scale chain the composite renderer uses**
  (crop expressions when smart framing is active, scale/pad/crop fallback
  otherwise), runs YuNet on each proxy frame, scales `(x, y, w, h)` boxes to
  canvas pixels, and dedupes across samples. Falls back to `[]` gracefully.
- **`RenderingService`** — `_render_clip` runs `detect_face_boxes` (in a
  thread) whenever `caption_engine != "legacy"`, passes the boxes through
  `_build_captions` → `build_motion_caption_ass` /
  `build_motion_caption_frames` → `clip_caption_request`. `face_margin`
  comes from the caption style (`CaptionStyleConfig.face_margin`, also added
  to the analysis preset config).
- **Tests**: 13 new tests — analyzer (empty when no model/cv2, canvas scaling,
  dedupe, crop-chain filter construction, pad fallback, decode-failure → [])
  and wiring (compiler → `Face` + `face-aware` placement, no faces → default
  placement, `clip_caption_request`/ASS/frames builders carry faces through).
  **232 passed / 2 skipped**; ruff clean except the 3 pre-existing E501s;
  full-repo mypy at baseline (54 pre-existing).

---

## 15. MotionCaption blueprint-driven caption theming — M4b

Second piece of the M4 lyrics-first wiring: the AI Director's editing
blueprint now themes captions and picks karaoke emphasis. The blueprint's
`global_style.subtitle_theme` is the richest caption direction available
(colors, animation, highlight words); it wins over preset + editor-style
defaults, and any missing/malformed field degrades to those defaults.

- **`lyrics/application/blueprint.py`** (new) — `caption_theme_hint(blueprint)`
  maps `editing_blueprint.global_style` to a frozen `CaptionThemeHint`:
  `colors[0..2]` → accent/muted/outline, `animation`/`word_animation` →
  a canonical MotionCaption strategy (unknown labels rejected), `style_name`
  → a known MotionCaption theme when it mentions one, and `highlight_words`
  normalized to lowercase.
- **`lyrics/application/theme.py`** — new public `normalize_animation(value)`
  that (unlike `animation_strategy`) rejects unknown labels so AI-provided
  animation names only apply when they map cleanly.
- **`lyrics/application/build.py`** — `clip_caption_request` gained `theme`
  and `highlight_words`; matching in-window words become clip-local
  `emphasis_indices` (karaoke emphasis) via new
  `emphasis_indices_for_words(...)`.
- **`lyrics/application/ass.py` / `frames.py`** — both builders pass `theme`
  and `highlight_words` through to the compiled `LyricsRequest`.
- **`RenderingService`** — `render_clips_with_captions` derives the hint from
  the video's stored blueprint and overlays the caption colors/animation onto
  the render style (after `apply_style_overrides`); `_render_clip` →
  `_build_captions` carry `theme` + `highlight_words` to the caption builders.
- **Tests**: 9 new tests — blueprint mapping (colors/animation/theme/
  highlights, word-animation fallback, malformed → none, invalid inputs
  ignored, style-name theme detection) + emphasis (matching, clip-local
  indices after windowing) + a `RenderingService` test asserting blueprint
  theming reaches the frames builder. **241 passed / 2 skipped**; ruff clean
  except the 3 pre-existing E501s; full-repo mypy at baseline (54).

---

## 16. Frontend caption-theme surface — M4c

The video detail page now shows the AI Director's per-video caption theme:
accent/muted/outline color swatches, the animation label, and the emphasis
words the karaoke pass highlights. This is read-only today — the theme is
regenerated by re-running analysis (the existing editing-style prompt) — so no
DB schema or new endpoint was needed; the analysis API already returned
`editing_blueprint`.

- **`frontend/src/lib/api.ts`** — `getAnalysis` now types
  `editing_blueprint: Record<string, unknown> | null`.
- **`frontend/src/app/dashboard/[projectId]/[videoId]/page.tsx`** — new
  `parseCaptionTheme(blueprint)` mirrors the backend `caption_theme_hint`
  mapping (colors → swatches, animation/word_animation, style_name badge,
  highlight words); the page loads the analysis once the video is analyzed
  and renders a "Caption theme" card under the status grid. `npx tsc --noEmit`
  clean; eslint only the pre-existing warnings.

---

## Current State

- **Test account**: `test@test.com` / `password123` (token cached at
  `/tmp/cf_token.txt`; project/video ids at `/tmp/cf_project.txt`,
  `/tmp/cf_video.txt`). Seed demo user: `demo@clipforge.ai` / `demo1234`.
- **Test video**: `/Users/kunalkoshta/Desktop/ClipForge-AI/video.mp4`.
- **Unit tests**: 241 passed / 2 skipped (`backend/.venv/bin/pytest tests/unit/
  -q`); ruff clean except 3 pre-existing E501s (`gemini_provider.py:64`,
  `clips/domain/ports.py:47`, `config.py:35`); mypy at baseline on the lyrics
  module and full repo; `npx tsc --noEmit` clean.
- Backend code is bind-mounted into Docker; restart api+worker to pick up
  code changes, but **recreating the worker container loses runtime-installed
  deps** (librosa/soundfile — reinstall with
  `docker exec clipforge-worker-1 pip install librosa soundfile`). Containers
  run `AI_PROVIDER=gemini`; mock is only used in unit tests. Host `python3`
  lacks deps — run backend commands inside containers.
- **M4 host-level end-to-end verification (passing)**: Docker/Gemini were not
  available (daemon down), so M4 was smoke-tested on the host with a synthetic
  540×960 clip through the *real* `RenderingService.render_clips_with_captions`
  (frames engine, blueprint with `FFD700`/`9E9E9E` + "moment"/"everything"
  highlights, YuNet sampled via a downloaded `face_detection_yunet_2023mar.onnx`
  at `OPENCV_FACE_MODEL`). Output: valid 6 s 1920×1080 MP4 + thumbnail, caption
  pixels present, and the t=2.0 frame shows **129 accent-gold pixels** on the
  active word + gray muted text — proving blueprint colors + karaoke emphasis
  land in the rendered video. Face-avoidance logic itself is covered by the
  M4a unit tests (the synthetic clip has no detectable face).

## Next Steps (candidate)

- Color-emoji font (Noto Color Emoji) in the api/worker image so emoji
  render in color.
- Show `hook_text` lower thirds for presets that disable them, or expose the
  toggle.
- Wire the `TransitionEngine` (fade/slide/zoom) into the render path.
- Expose `editing_plan_json` (or a summary) through the clips API + frontend.
- S3 provider, resumable multipart uploads, caption overlay/timeline editor
  (see `flow.md` §12).

### MotionCaption lyrics integration follow-ups (M4)

- **M4 — lyrics-first wiring**: ✅ face-aware placement (M4a); ✅ blueprint →
  karaoke emphasis/theme (M4b); ✅ per-video caption theme in the frontend
  (M4c); ✅ `flow.md` refresh + host-level end-to-end verification. **M4 is
  complete.** A Docker/Gemini live pass remains worthwhile before cutting a
  release.

### M4/M5 follow-ups (approve next milestone)

- **M5 — plugin renderer**: new `plugins/` module with one plugin per track
  (camera / subtitle / transition / overlay / emoji / color / music / sfx),
  each exposing `apply()`. Per-clip renders execute only in-window events from
  the blueprint; the legacy `CompositeRenderer` stays as fallback for videos
  without a blueprint.
- **M6 — final assembly**: an assembler concatenates the rendered clips with
  the blueprint's transitions + global grade/music into a final cut; frontend
  shows the final video.
- Re-process support: allow re-running analysis on a `ready` video (currently
  blocked by unique `video_id` on `transcripts`/`analysis_results` — the
  live-verify workaround was to delete the old rows).

- Fix the worker `asyncio.Lock bound to a different event loop` flake (shared
  engine `_exec_once_mutex` across dramatiq threads) and add a
  `workflow_reconcile` scheduler (cron/loop) so crashed runs self-heal.
- Re-process support: allow changing the prompt on a `ready` video and
  re-running (reset jobs/clips/artifacts first).
- Use `punch_ins[].strength` to vary zoom scale / SFX volume at render time
  (variable-intensity emphasis).
- Wire real shot boundaries → `cut_points` for auto-cutting clips at scene
  breaks (needs pyscenedetect available somewhere).
- Move intelligence workers to their own process/queue with a bounded worker
  pool once scene/motion cost matters.
- Status/artifacts read API so the frontend can show per-worker progress.
