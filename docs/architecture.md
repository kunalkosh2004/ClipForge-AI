# ClipForge AI — Architecture (current implementation)

> Status: documents the architecture as implemented at HEAD (M4 director
> contract + M5 smart re-framing). For end-to-end request flows see
> `docs/flow.md`; for the target redesign see `docs/architecture-v2.md`.

---

## 1. Topology

```
 Browser (Next.js)
      │
      ▼
┌─────────────┐    PostgreSQL    Redis            S3 / MinIO
│ FastAPI API │◀───  :5436  ◀───  :6382  ◀──────── object storage
│   :8000     │
└──────┬──────┘
       │ enqueue (Redis streams via queue port)
       ▼
┌─────────────┐   queues: default / ai / media / render / import / dead
│ Dramatiq    │
│ Worker      │
└──────┬──────┘
       ├──► FFprobe / FFmpeg   (metadata, clip cutting, rendering)
       ├──► librosa/soundfile  (beat + audio analysis)
       ├──► Gemini / Mock AI   (transcribe, video understanding, director)
       └──► YuNet + motion     (face tracking / smart re-framing)
```

Four containers: `clipforge-api-1`, `clipforge-worker-1`,
`clipforge-postgres-1`, `clipforge-redis-1`.

## 2. Module layout (hexagonal per module)

Each feature module follows `domain / application / infrastructure`:

| Module | Responsibility |
|---|---|
| `videos/` | project & video entity, signed-URL upload, status lifecycle |
| `identity/` | auth (JWT), users, API keys |
| `storage/` | object-storage provider (S3/MinIO/FS) |
| `queue/` | broker port (Redis streams behind `QueuePort`) |
| `intelligence/` | M1/M2 workers: `metadata`, `beat`, `motion`, `scene`, `timeline` |
| `artifacts/` | blob `ArtifactStore` + index `ArtifactRepository` for worker JSON |
| `analysis/` | `analysis_results` + `transcripts`, presets, `AnalysisService` |
| `directing/` | M4 director: `EditingBlueprint`, prompt, normalizer, `DirectingService` |
| `timeline/` | deterministic timeline engine (shot scoring, punch-ins, cuts) |
| `clips/` | clip entity + thumbnail generation |
| `rendering/` | caption/camera/audio/transition/overlay/color domain + `RenderingService` |
| `processing/` | durable `JobTracker` (jobs table, dedupe, retry accounting) |
| `workflow/` | stage orchestration / workflow nodes |
| `events/` | Redis pub/sub status notifier + SSE |
| `worker/tasks.py` | dramatiq tasks = the pipeline stages |
| `ai/` | `AIProvider` (Gemini + Mock), key/model fallback, usage callback |
| `usage/` | per-call token/cost accounting (`ai_model_usage`) |
| `admin/` | admin API |

## 3. Pipeline (5 stages, dramatiq tasks)

```
upload/complete
   │
   ▼
1. metadata_extraction   (QUEUE_DEFAULT)  ffprobe → duration/fps/res/audio; status=metadata_extracted
   │  (enqueues intelligence artifacts in parallel)
   │      beat/motion/scene workers (QUEUE_MEDIA) → artifacts → timeline engine
   │  (then enqueues ai_analysis)
   ▼
2. ai_analysis           (QUEUE_AI)  Gemini: transcribe → analyze_video → director(direct)
   │  → transcript + words  → understanding  → editing_blueprint  → legacy editing_plan
   │  (then enqueues clip_extraction)
   ▼
3. clip_extraction       (QUEUE_DEFAULT)  cut blueprint clips from source → thumbnails
   ▼
4. render                (QUEUE_RENDER)   captions + beat-timed zooms + audio + re-frame
   │                                       each clip → upload → final cut
   ▼
5. ready / failed + dead_letter (QUEUE_DEAD)
```

Retries: 5 with exponential backoff per task; exhausted messages route to the
`dead_letter` actor. All stages are idempotent via JobTracker dedupe keys
(`{video_id}:{stage}`).

## 4. AI provider abstraction (`ai/`)

- `AIProvider` protocol with operations: `transcribe`, `analyze` (video
  understanding), `direct` (M4 director). Implementations: `GeminiProvider`,
  `MockAIProvider`.
- `GeminiProvider` keeps a fallback chain of API keys × models; a failing
  key/model advances the chain. Every call reports usage via a callback →
  `ai_model_usage`.
- Schema handling: pydantic `responseSchema` is stripped of
  `additionalProperties` for the Gemini Developer API (`_schema_for_gemini`).
- Config: `GEMINI_MODEL`, `GEMINI_MODELS` (chain), `GEMINI_API_KEY(S)`,
  daily token/request limits.

## 5. Director contract (`directing/`, M4)

`AnalysisService.run_analysis` orchestrates: transcribe → analyze →
`AIProvider.direct` → normalize → persist `editing_blueprint` (JSONB) +
legacy `editing_plan`.

`EditingBlueprint` (schema_version 1):
- `global_style`: color grading, subtitle theme, music, camera/editing philosophy
- `clips`: source windows with `hook`, `thumbnail_text`, `viral_score`,
  `retention_score`, `story_role`
- `timeline.events`: per-track typed events with `timestamp` / `duration` /
  `parameters` / `reason`

Tracks: `camera`, `subtitle`, `transition`, `overlay`, `emoji`, `music`,
`effects`, `cta`. Events use source-video seconds; the renderer applies only
events inside each clip window (shifted to clip-local time).

The normalizer coerces raw AI output into the typed schema and drops
non-conforming events (logged as `blueprint_events_dropped`).

## 6. Deterministic layers

- **Timeline engine** (`timeline/domain/engine.py`): pure function over
  scenes/motion/beats → shot emphasis scores, punch-ins, cut points. No I/O.
- **Renderer** (`rendering/`): `RenderingService` reads analysis + transcript +
  preset/style + blueprint, and drives ffmpeg to composite captions, zooms,
  transitions, overlays, audio beds, and smart re-framing (YuNet face +
  motion-tracking crop). Creative defaults come from presets + plan overrides;
  per-clip failures keep the raw cut and are logged, not fatal.

## 7. Data model (key entities)

- `videos` (status lifecycle), `projects`
- `analysis_results` (`understanding`, `editing_plan`, `editing_blueprint` JSONB)
- `transcripts` (`segments` + `words` JSONB, language)
- `clips` (start/end, storage keys, render state, `editing_plan_json`)
- `jobs` (type, status, attempts, dedupe_key, last_error)
- `ai_model_usage` (per-call model/operation/tokens/key)
- `artifacts` (index of worker JSON blobs)

## 8. Ports & provider seams

- `common/ports.py`: `StorageProvider`
- `queue/`: `QueuePort` (Redis streams; broker swappable)
- `artifacts/domain/ports.py`: `ArtifactStore`, `ArtifactRepository`
- `clips/domain/ports.py`, `videos/domain/ports.py`, `analysis/domain/ports.py`
- `rendering/domain/ports.py`: `CaptionRenderer`, `FramingAnalyzer`

Everything above is constructor-injected (see `container.py`) — no globals,
testable with in-memory/fake ports.

## 9. Config & ops

- Pydantic `Settings` (`config.py`): DB/Redis/queue names, AI provider + models,
  storage, JWT, feature flags.
- Alembic migrations in `backend/alembic/versions/` (head `d3e4f5a6b7c8`).
- Tests: `backend/tests/unit` (+ live integration); gates = pytest, ruff,
  mypy, `npx tsc --noEmit`.
