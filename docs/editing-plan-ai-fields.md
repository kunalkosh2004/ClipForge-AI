# Editing Plan — AI-Driven Per-Clip Fields (Implementation Plan)

> Status: **implemented** (M6 — user-driven editing-style prompt). The scope grew
> from the original four fields: the frontend now captures a free-text editing
> request, it is stored on the video, fed into `generate_editing_plan`, mapped by
> the AI into a plan-level `style` object plus per-clip fields, and applied at
> render time.
> Goal: enrich the AI's `generate_editing_plan` output so the editing/render
> pipeline uses more of what the model already knows about each clip.

## What was built (M6)

- **Frontend**: free-text "Editing style" textarea on the project page; sent with
  `POST /api/v1/videos` as `editing_style`.
- **Storage**: new `videos.editing_style` column (migration
  `c1e2d3e4f5a6`), threaded through the `Video` entity and repositories.
- **AI**: `generate_editing_plan(video, preset, context, editing_style)`; Gemini
  maps the request to a plan-level `style: EditorStyle` (caption_style,
  caption_colors, transition_style, sfx_enabled, sfx_types, music_mood,
  music_volume_db, emojis_enabled, punch_zooms, zoom_intensity, cta_enabled,
  cta_text) plus per-clip `emphasis_times`, `emoji_triggers`, `cta_text`,
  `hook_text`. Mock provider mirrors the shape.
- **Normalizer**: sanitizes/dedupes clip-local emphasis times and emoji
  triggers in both rebuild passes; passes `style` through.
- **Rendering**: `apply_style_overrides(RenderStyle, overrides)` layers the
  plan directives over the preset; `_render_clip` merges AI emphasis times with
  audio beats, feeds `emoji_triggers`/`cta_text`/`hook_text` into the composite,
  and picks the SFX synth kind from `sfx_types`. Caption accent color is now
  threaded into the ASS (`build_caption_ass(..., accent_color=...)`).

### Live verification (real Gemini, video `019fd8d4-64b8-7bc0-94bb-87bd128a983c`)

Plan-level style came back populated (`caption_style: karaoke`,
`caption_colors: ["FFFF00","FFFFFF"]`, `punch_zooms`, `zoom_intensity: 0.3`,
`emojis_enabled`, `cta_enabled` + `cta_text: "Subscribe"`, `sfx_types:
["whoosh"]`, `music_mood: upbeat`, `music_volume_db: -3.0`); every clip carried
`hook_text`, `emphasis_times`, and `emoji_triggers`. 4/4 clips rendered; the
generated ASS contained the 🔥 emoji event, the "Subscribe" CTA, yellow caption
accent, and zoom pulses at the AI emphasis times.

---

## 1. Why

`generate_editing_plan` already tells us *which* moments are engaging (start/end,
hook, viral_score, emotion, category), but the renderer only consumes **start/end**
(clip boundaries) and **hook** (clip title → lower-third text). Several render
capabilities that are already wired up are never fed data:

| Capability (code exists) | Currently fed by | Status |
|--------------------------|------------------|--------|
| Punch/emphasis zoom (`ZoomEngine`) | audio-energy beats (`metadata_json.audio.peaks`) | Generic, not per-clip semantic |
| SFX triggers | derived from the same beats | Generic |
| Emoji overlay (`OverlayEngine`) | nothing | **Dead — never populated** |
| CTA overlay (`CTAOverlay`) | preset config only | No per-clip control |
| Lower third | `clip.title` (the hook) | Hook and title conflated |

Adding a small, focused set of per-clip fields lets the AI drive these directly.

---

## 2. Proposed new per-clip fields

All optional (defaults provided) so persisted plans from older runs stay valid
and Gemini is free to omit them.

| Field | Type | Semantics | Feeds |
|-------|------|-----------|-------|
| `emphasis_times` | `list[float]` | Seconds (clip-local) to punch/emphasize | `ZoomEngine.build_zoom_plan(emphasis_times=...)`, SFX |
| `emoji_triggers` | `list[{emoji, time}]` | Emoji + clip-local second | `OverlayEngine.build_plan(emoji_triggers=...)` |
| `cta_text` | `str \| None` | Per-clip call-to-action text | `CTAOverlay` |
| `hook_text` | `str \| None` | On-screen hook headline, distinct from title | lower-third / hook overlay |

### Schema sketch (`backend/src/clipforge/common/ports/ai_provider.py`)

```python
class EmojiTrigger(BaseModel):
    emoji: str
    time: float

class ClipCandidate(BaseModel):
    start_time: str | float
    end_time: str | float
    hook: str | None = None
    why_it_is_engaging: str | None = None
    viral_score: float = 0.0
    emotion: str | None = None
    category: str | None = None
    thumbnail_text: str | None = None
    # new:
    emphasis_times: list[float] = Field(default_factory=list)
    emoji_triggers: list[EmojiTrigger] = Field(default_factory=list)
    cta_text: str | None = None
    hook_text: str | None = None
```

---

## 3. Files to change (checklist)

1. **`backend/src/clipforge/common/ports/ai_provider.py`**
   - Add `EmojiTrigger` model; extend `ClipCandidate` (see sketch above).

2. **`backend/src/clipforge/ai/gemini_provider.py`** — `generate_editing_plan`
   - Prompt: ask for the new fields with hard constraints:
     - `emphasis_times`: numeric seconds **within** the clip window; 1–4 moments.
     - `emoji_triggers`: short list `[{"emoji": "🔥", "time": 12.5}]`, times in-window.
     - `cta_text`: short phrase (≤ 4 words).
     - `hook_text`: headline ≤ 40 chars, distinct from `hook`.
   - Update the example clip in the prompt to show the new keys.

3. **`backend/src/clipforge/ai/mock_provider.py`** — `generate_editing_plan`
   - Return sample values for the new fields (keeps mock/unit tests in parity).

4. **`backend/src/clipforge/analysis/application/normalizer.py`** — **the footgun**
   - `normalize_editing_plan` rebuilds `ClipCandidate` in **two** places:
     1. the `cleaned` loop (≈ lines 40–50),
     2. `_extend_short_clips` (≈ lines 95–105).
   - Thread the new fields through **both**, and sanitize:
     - `emphasis_times` → drop entries outside `[start, end]`, round to 3dp,
       sort, de-dupe, cap to ~8.
     - `emoji_triggers` → drop entries with empty `emoji` or out-of-window `time`.
   - Plan-level: nothing new needed (fields live per-clip).

5. **`backend/src/clipforge/rendering/application/service.py`** — `_render_clip`
   - Read the per-clip fields from `clip.editing_plan_json`.
   - `emphasis_times` = AI `emphasis_times` **merged** with the existing
     audio-beat times (union, sorted, in-window).
   - Pass `emoji_triggers=...` and `cta_text=...` into
     `CompositeRenderer.render_clip` (params already exist).
   - `lower_third_text` = `hook_text or clip.title`.

6. **`backend/src/clipforge/rendering/domain/composite.py`**
   - No structural change expected — `emoji_triggers`, `cta_text`,
     `lower_third_text` params already exist and flow to
     `OverlayEngine.build_plan`. Only verify the `emoji_triggers` → ASS
     rendering path emits valid dialogue lines.

7. **Tests**
   - `backend/tests/unit/test_rendering_service.py`:
     - assert AI `emphasis_times` reach `composite` (captured kwargs).
     - assert `emoji_triggers` / `cta_text` / `hook_text` pass through.
   - New `backend/tests/unit/test_normalizer.py`:
     - new fields survive `normalize_editing_plan` and `_extend_short_clips`.
     - out-of-window `emphasis_times` / `emoji_triggers` are dropped.

---

## 4. Non-goals (defer)

| Idea | Why deferred |
|------|--------------|
| Per-clip `transition` (fade/slide/glitch) | `TransitionEngine` (`rendering/domain/transitions.py`) is **not wired into the render path** at all — would need a separate feature first. |
| Music mood / energy per clip | No per-clip audio plumbing (music bed is generated once per clip from BPM only). |
| Per-clip color/theme | Would require style-system plumbing; cosmetic, low ROI for now. |

---

## 5. Risks & guardrails

- **Normalizer field-drop bug:** the two `ClipCandidate` rebuild sites mean new
  fields can silently disappear. Unit tests must assert round-trip survival.
- **Hallucinated timestamps:** Gemini may emit times outside the clip window or
  non-numeric strings. Normalizer clamps/drops (see checklist item 4).
- **Cost/latency:** more output tokens per call. Keep prompts tight and fields
  optional so the model can omit them rather than pad.
- **Backward compatibility:** all new fields optional with defaults; old stored
  `editing_plan_json` documents remain valid.

---

## 6. Acceptance criteria

1. A clip rendered with mock AI supplying all four new fields shows:
   - a zoom punch at an AI-suggested `emphasis_time`,
   - an emoji overlay at the trigger time,
   - the per-clip `cta_text` overlay,
   - `hook_text` (not the raw hook) as the lower third.
2. `normalize_editing_plan` preserves all new fields and drops out-of-window ones.
3. Full Gemini pipeline still renders; `ruff` + `pytest` green.
