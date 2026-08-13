# ClipForge AI — Architecture v2 (AI Systems Design)

> Status: design proposal — no code changes yet. Approvals gated per phase.
> This document replaces the mental model of "AI watches video → edits" with a
> layered, artifact-driven pipeline in which every stage is a replaceable,
> testable, single-responsibility module. The differentiator: **the system edits
> timelines, not just videos.**

---

## 1. Design Principles

1. **Artifacts are the contract.** Every stage communicates through immutable,
   versioned, typed JSON documents in the Artifact Store. Nothing reads a
   sibling's internal state. Nothing re-derives work another stage already did.
2. **AI reasons; machines execute.** Only the Director makes creative decisions.
   The Compiler, Physics Engine, and Renderer are deterministic and never
   invent motivation.
3. **One responsibility per module.** A worker extracts one signal. A plugin
   applies one track. A service orchestrates, never computes.
4. **Replaceable by design.** Workers and plugins are registered by kind; the
   pipeline drives registries, not hard-coded imports. Swap a worker or a
   plugin without touching anything else.
5. **Deterministic rendering.** Identical artifacts + identical timeline
   ⇒ identical pixels. Rendering is a pure function of inputs, so it is
   testable, cacheable, and diffable.
6. **Fault tolerance over optimism.** Missing artifacts degrade the pipeline
   gracefully (never crash the whole video); every stage is idempotent;
   retries and dead-letters are explicit.
7. **Human in the loop.** The timeline is an editable contract. Users and the
   NL Edit Engine both mutate it; the Diff Engine turns change into a minimal
   re-render.

---

## 2. System Overview

```
 Source Video
     │
     ▼
┌────────────────────┐
│ Metadata Layer     │  metadata.json        (ffprobe: duration/fps/res/…)
└─────────┬──────────┘
          ▼
┌────────────────────┐    one JSON per worker, all replaceable
│ Perception Layer   │  scenes.json  beats.json  faces.json  objects.json
│ (worker registry)  │  ocr.json    motion.json  colors.json emotion.json
└─────────┬──────────┘  speech/transcript.json + words.json  retention.json
          │
          ▼          ╔══════════════════╗  ╔══════════════════╗
┌────────────────────┐║  User Intent    ║  ║  Style Profile   ║
│ AI Director        │║  (brief, ops)   ║  ║  (MrBeast, Holi, ║
│ (Gemini reasoning) │╚════════╤════════╝  ╚═════╤════════════╝
│  — never raw video ┘         │ (intent)        │ (style)
└─────────┬────────────────────┴─────────────────┘
          ▼
   editing_blueprint.json      (intent only — NO rendering instructions)
          ▼
┌────────────────────┐
│ Timeline Compiler  │  deterministic: blueprint + artifacts → tracks
└─────────┬──────────┘
          ▼
    timeline.json     (typed events: timestamp/duration/parameters/reason/priority/dependencies)
          │
          ├──────────────────────────────┐
          ▼                              ▼
┌────────────────────┐          ┌────────────────────┐
│ Human Editable     │          │ Physics Engine     │  intent → keyframes
│ Timeline (API)     │◀─ edit ──│ (camera/motion,    │  scale/rot/pos/easing
└─────────┬──────────┘          │  easing curves)    │  bezier/spring/overshoot
          │                     └─────────┬──────────┘
          ▼                               ▼
┌────────────────────┐          ┌────────────────────┐
│ NL Edit Engine     │          │ Renderer           │  pure executor
│ "make it faster"   │          │ (plugin registry)  │  subtitle/camera/
└─────────┬──────────┘          │ transition/emoji/  │  color/audio/effects
          ▼                     └────────────────────┘
┌────────────────────┐                 ▲
│ Timeline Diff      │                 │
│ Engine (minimal    │── re-render ────┘  (incremental: only changed clips)
│  change detection) │
└────────────────────┘
```

### The core innovation

Today AI edits a video once and ships it. This system makes the **timeline** the
editable, first-class product:

- The Compiler emits `timeline.json`, a human-editable, versioned contract.
- **NL Edit Engine** turns natural language ("more cinematic", "less zoom",
  "emphasize the drops") into *structured edit operations* applied to the
  timeline — never into raw pixels.
- **Timeline Diff Engine** computes a minimal, event-level diff between the old
  and new timelines and triggers **incremental re-render** of only the affected
  clips, reusing cached output for everything else.

This is what makes ClipForge feel like an AI-native editor rather than an
AI clip generator.

---

## 3. Pipeline Layers (phased)

### Phase 1 — Metadata Layer (exists, formalize)

`intelligence/workers/metadata.py` already emits `metadata.json`
(duration/fps/resolution/codec/orientation/aspect/audio). Formalization only:

- Pin the `metadata.json` schema (see §4) with a Pydantic model + contract test.
- Make it the clock for every downstream worker (duration source of truth).

### Phase 2 — Perception Layer (worker registry)

Each worker: one video → one artifact JSON. Independent, replaceable, parallel.

| Worker | Artifact | Source |
|---|---|---|
| Scene | `scenes.json` | scene detection / VLM |
| Beat | `beats.json` | audio analysis (librosa) |
| Face | `faces.json` | face detect + track (YuNet/MediaPipe) |
| Object | `objects.json` | object detect (YOLO) |
| OCR | `ocr.json` | text overlay detection |
| Motion | `motion.json` | optical flow / frame diff |
| Color | `colors.json` | histogram / palette / LUT stats |
| Emotion | `emotion.json` | expression classifier |
| Speech | `transcript.json` + `words.json` | ASR (WhisperX) |
| Retention | `retention.json` | retention model (see §9) |

**Worker interface** (`intelligence/workers/base.py` → formalized):

```
PerceptionWorker(ABC):
    kind: str                                   # "scenes", "faces", ...
    input_artifacts: tuple[str, ...]            # deps (e.g. beat needs metadata)
    output_artifact: str
    schema: type[ArtifactSchema]
    provider: ProviderConfig                     # may be local, ffmpeg, or AI
    async def extract(ctx) -> dict               # returns the artifact payload
```

Registration in a **WorkerRegistry** keyed by `kind`. The orchestrator resolves
dependencies from `input_artifacts` and runs ready workers concurrently. Adding
a future worker (Meme, Sports, Gaming, Podcast, Anime, Reaction) is *only*
adding a registry entry + artifact schema — zero pipeline changes.

Pixel-level work stays in perception workers behind the registry; a vision
perception worker may use an LLM/VLM for *its specific signal*, but the
Director never does.

### Phase 3 — AI Director (reasoning engine)

The biggest architectural change: **Gemini stops watching the raw video.**

Instead, the Director receives the complete **artifact pack**:

```
metadata.json + scenes.json + beats.json + faces.json + objects.json +
ocr.json + motion.json + colors.json + emotion.json + retention.json +
transcript.json + words.json
```

Its only job: understand the story, choose clips, and design the edit.
It returns `editing_blueprint.json` — **editing intent, never pixels**:

- `schema_version`
- `style_profile` (reference to a Style Engine profile)
- `global_style`
- `story_structure` (arc: hook/turn/payoff/climax, per-clip roles & scores)
- `editing_philosophy`
- `clips` (source windows with reason + retention justification)
- `camera_strategy` (punches, push-ins, pacing, why)
- `subtitle_strategy` (karaoke, emphasis, typography intent)
- `transition_strategy`
- `color_strategy`
- `audio_strategy`
- `timeline_intent` (per-track high-level beats: "punch zoom at 0:23 for the
  Holi throw", "emoji ❤️ at the first smile")

The Director is *explicitly prohibited* from emitting renderer commands
(no ffmpeg filters, no exact keyframes). Intent only. The existing
`directing/` module (blueprint + prompt + normalizer + service) is retained
and reframed: prompt context switches from video-understanding output to the
artifact pack; schema is extended with the strategy fields above.

**Provider abstraction.** `AIProvider` (Gemini/OpenAI/mock) already routes
operations (`direct`/`analyze`/`transcribe`) across key+model fallback chains.
Keep it; add per-worker provider routing and per-operation schema versioning.

### Phase 4 — Timeline Compiler

A separate, deterministic service (`timeline/` grows from the M2 engine into a
full compiler).

Inputs: `editing_blueprint.json` + the artifact pack.
Output: `timeline.json`.

Responsibilities (all deterministic):
1. **Normalize + validate** intent events against the track vocabulary
   (moves the M4 normalizer here).
2. **Resolve clips** into a playable sequence (start/end, in/out handles,
   ordering), honoring the gap policy (flat/trust director).
3. **Materialize tracks**: `camera`, `subtitle`, `transition`, `overlay`,
   `emoji`, `music`, `effects`, `color`, `cta`.
4. **Dependency resolution**: events carry `dependencies` (e.g. a transition
   depends on the preceding clip; a subtitle depends on `words.json`).
   Topological order is computed by the compiler, not by the AI.
5. **Priority + conflict policy**: overlapping events on a track are resolved
   deterministically (priority field wins; explicit policy, not randomness).

Every event: `{ track, type, timestamp, duration, parameters, reason,
priority, dependencies }`.

### Phase 5 — Physics Engine (new module)

The timeline must not contain naive "zooms". It contains **motion intent**;
the Physics Engine converts intent into cinematic motion.

- Input: camera/transition events from `timeline.json` (plus beat/face/motion
  artifacts for grounding).
- Output: **keyframed motion** — keyframes with `scale`, `rotation`,
  `position`, `easing`, `velocity`, plus **motion curves**.

Supported easing: `bezier`, `ease-in`, `ease-out`, `ease-in-out`, `spring`,
`overshoot`, `bounce`.

Example — Director says "punch zoom":
```
→ Physics Engine emits a scale curve that accelerates hard, overshoots 3%,
  settles with ease-out, timed to the beat at the target second.
```
A `push_in` becomes a slow, eased scale ramp with rule-of-thirds reframing
anchored to the tracked face center. Everything interpolates smoothly and is
backed by the existing `framing.py` (YuNet face + motion tracking crop) —
reframed as *consumers of physics output*, not deciders.

The Physics Engine is a pure math module: identical input ⇒ identical
keyframes, trivially unit-testable (property tests on easing monotonicity,
continuity, no time reversals).

### Phase 6 — Renderer (pure executor)

The Renderer never thinks. It executes `timeline.json` (already post-physics)
through a **PluginRegistry**.

Plugins (each implements `apply()`, each independent):

| Plugin | Responsibility |
|---|---|
| Subtitle | word-level karaoke/pop/fade/bounce/blur/highlight, emoji-inline, adaptive line breaking, safe area |
| Camera | virtual camera: pan/tilt/zoom/push-in/out, smart crop, rule of thirds |
| Transition | cuts, whip, flash, fade — driven by physics curves |
| Overlay | branding, image overlays, CTA |
| Particle | holi powder, confetti, sparkles (FFmpeg or GL filter chains) |
| Audio | whoosh, boom, ducking, echo, limiter, normalize, beat sync |
| Emoji | animated emoji placement on the emoji track |
| Color | LUT, bloom, glow, contrast, grain, sharpen, noise reduction, skin-tone protection |
| Effects | vignette, blur, glows |

Plugin interface:

```
RendererPlugin(ABC):
    track: str
    schema: type[EventSchema]
    async def apply(ctx: RenderContext, event: TimelineEvent) -> FilterBatch
```

The service (`rendering/application/service.py`) shrinks to an orchestrator:
pull timeline → for each track resolve plugin → collect filter batches → hand
to the composite encoder. **All creative defaults move out of the renderer**
(preset/style resolution lives in the Compiler + Style Engine).

---

## 4. Artifact Store & Schemas

The existing `artifacts/` module (blob `ArtifactStore` + index
`ArtifactRepository`) is the backbone. Formalize:

- **`artifact_schemas/`**: one Pydantic model per artifact kind, each tagged
  `schema_version`. A **SchemaRegistry** validates every write and enables
  migration/backfill on version bumps (versioned JSON, not overwritten blobs).
- **Immutable, versioned blobs**: `(video_id, kind, schema_version, created_at)`
  in object storage; the index points at latest. Re-running a worker writes a
  new blob — idempotent, replayable, auditable.
- **Artifact dependency graph**: each artifact records its `input_artifacts`
  and producer (worker + provider + model + tokens for cost accounting).

Missing-artifact policy is explicit per consumer (the M2 timeline engine
already degrades gracefully; extend that discipline everywhere).

## 5. Orchestration & Typed Events

`workflow/` + `events/` formalize into an event-driven DAG:

- Workers/compiler/renderer **emit typed events** (`artifact.written`, 
  `blueprint.ready`, `timeline.compiled`, `clip.rendered`, …) to Redis.
- The **orchestrator** subscribes, resolves the artifact dependency graph, and
  starts only stages whose inputs are satisfied.
- `processing/` JobTracker stays as the durable state; `jobs` rows track
  stages, attempts, and last_error for observability and retry.
- Queues by concern (`metadata/media/ai/render`) already exist; keep them.
  The `queue/` port keeps the broker swappable (Redis streams today, Celery/SQS
  later — the abstraction already exists; do not force a broker rewrite).

## 6. Style Engine (profiles, not prompts)

Replace prompt-embedded styling with **versioned style profiles**:

`MrBeast`, `Alex Hormozi`, `Netflix Documentary`, `Bollywood`,
`Punjabi Music Video`, `Podcast`, `Gaming`, `Minimal`, `default`.

Each profile is a typed, auditable document parameterizing:
camera behavior, caption theme, transitions, effects, audio, color,
pacing/rhythm targets, safe-area and format rules.

- The **Director** selects a profile and composes it with the video's story
  (the blueprint's `style_profile` + `global_style`).
- The **Compiler** applies the profile to produce track parameters.
- Profiles are data (JSON), versioned, swappable — a designer can restyle a
  whole pipeline without touching code. Existing `analysis/domain/presets.py`
  and `RenderStyle.from_preset` migrate into this engine.

## 7. Retention Engine

A dedicated perception worker predicting *attention*:

Output `retention.json`:
- `viewer_drop` risk curve (where people leave)
- `viewer_interest` score curve
- `visual_density`, `speech_density`, `emotion_density`, `motion_density`

The Director reads `retention.json` while choosing clips and writing
`timeline_intent` (e.g. "hook inside 3s because drop risk peaks at 5s"). The
Retention Engine is a registry worker like any other — its model is replaceable
(e.g. swap in a learned model later).

## 8. Future Workers (extensibility)

Adding `Meme`, `Sports`, `Gaming`, `Podcast`, `MusicVideo`, `Anime`,
`Reaction` workers = new registry entries + artifact schemas + optionally a
style profile. No changes to the Director contract, Compiler, Physics Engine,
or Renderer. The Director simply receives one more artifact in its pack.

## 9. The Innovation: NL Edit Engine + Timeline Diff Engine

### Editable timeline

`timeline.json` is a **versioned, public contract** exposed over the API
(`timeline/` module). Users (or the product) can read, edit, and re-submit it.
Every revision is stored (immutable blobs, same as artifacts).

### NL Edit Engine

```
Input: "make it faster" / "more cinematic" / "less zoom" / "more emotional"
        + the current timeline.json + (optional) current artifact pack
Step 1  Intent Parser → a structured EditOp:
        { op: "tempo", factor: 1.3 }            (drop dead time, tighten gaps)
        { op: "camera_intensity", delta: -0.5 }  (reduce punches per minute)
        { op: "emotion_boost", tracks: ["emoji","color"], strength: 0.3 }
        { op: "retarget", clip: "c3", beat: 23.0 }
Step 2  EditOp Applier → new timeline.json
        Each op is deterministic over the timeline, applied track-aware,
        respecting `priority` and `dependencies`. Ops are pure functions so
        they are testable and undoable (op history = undo stack).
```

The intent model is deliberately small and typed (an enum of op kinds), which
keeps it predictable. It is *not* a free-form prompt-to-pixels generator.

### Timeline Diff Engine

Computes an **event-level minimal diff** between `timeline_old` and
`timeline_new`:

- `added` / `removed` / `modified` events (modified = parameter/timestamp deltas)
- affected clip ids (which source windows' render output changes)
- a **re-render plan**: render only affected clips; reuse cached output for the
  rest; final-cut reassembly is cheap.

Because rendering is deterministic and keyed by `(clip, timeline_revision)`,
the diff engine gives near-instant iteration: most edits touch 1–3 clips, so
most re-renders are seconds, not minutes.

---

## 10. Cross-Cutting Concerns

- **Idempotency**: every stage writes immutable artifacts; re-running a stage
  overwrites-at-new-version, never corrupts. Job dedupe keys already exist
  (`processing/`).
- **Retries/DLQ**: existing task retry + dead-letter pattern stays; per-stage
  `max_retries` from the registry.
- **Cost & usage**: `ai_model_usage` records per-operation tokens/key/model;
  extend to perception workers and the Director's artifact-pack prompt.
- **Observability**: keep structured logs + traces per stage; add artifact
  provenance to traces (`artifact.written` spans).
- **Determinism tests**: golden outputs for compiler + physics + renderer
  (same inputs → same bytes).
- **Contract tests**: every artifact schema validated on write; every plugin
  validated against its track.

## 11. Mapping: existing code → target

| Target layer | Existing module | Gap |
|---|---|---|
| Metadata | `intelligence/workers/metadata.py` | pin schema + contract test |
| Perception registry | `intelligence/workers/base.py`, `beat/motion/scene` | registry + face/object/ocr/color/emotion/retention + speech split |
| Artifact store | `artifacts/` | schema registry + versioned blobs + provenance |
| Director | `directing/` (blueprint/prompt/normalizer/service) | artifact-fed prompt (no raw video), strategy fields, style_profile |
| Timeline compiler | `timeline/domain/engine.py` + M4 normalizer | full tracks, priority, dependencies, profile application |
| Physics engine | `rendering/domain/framing.py`, `zoom.py` | keyframes + easing module (new) |
| Renderer | `rendering/` (composite, captions, audio, styles, transitions, overlays) | plugin registry, remove creative defaults |
| Style engine | `analysis/domain/presets.py`, `RenderStyle.from_preset` | typed versioned profiles |
| Orchestration | `workflow/`, `events/`, `worker/tasks.py`, `processing/` | artifact DAG + typed events |
| NL Edit + Diff | — | new (the innovation) |

## 12. Phased roadmap (approval gates)

| Phase | Scope | Gate |
|---|---|---|
| **A. Architecture** | this document approved | ✅ review this doc |
| **B. Artifact core** | schema registry, versioned artifacts, worker registry + retention worker | approval |
| **C. Director on artifacts** | Director reads artifact pack (no raw video), blueprint v2 fields | approval |
| **D. Timeline Compiler v2** | blueprint → full `timeline.json` (tracks, priority, deps) | approval |
| **E. Physics Engine** | camera keyframes + easing; wire into renderer | approval |
| **F. Renderer plugins** | plugin registry; move defaults to compiler/style engine | approval |
| **G. Style Engine** | profile docs + application | approval |
| **H. NL Edit + Diff** | editable timeline API, edit ops, diff engine, incremental re-render | approval |

Each phase keeps gates green (tests, lint, types) and does not rewrite working
modules that already implement the target behavior — it moves them into their
target layer.

---

## 13. Open decisions for the user

1. **Director vision**: strict "never watch video" (perception must cover all
   signals) vs. pragmatic hybrid (Director may receive a low-res thumbnail
   contact sheet for story comprehension, but all pixel decisions stay in
   workers). Recommend hybrid-first.
2. **Perception provider strategy**: local (librosa/YuNet/YOLO) for cheap
   signals, Gemini/WhisperX only for speech + scene description — confirm the
   cost/latency budget.
3. **Timeline as public API**: how much of `timeline.json` to expose for human
   editing in v1 (full contract vs. read-only preview).
4. **NL Edit scope**: start with the small typed op set (§9) — confirm no
   free-form prompt-to-pixels in v1.
