# Project Memory — ComfyUI-BigBunnyBall-Nodes

> Durable project state for this ComfyUI custom-nodes pack. Maintained by Hanako (since 2026-09-06).
> Ingested from handoff doc `comfyui-node-tutoring-session.md` (2026-08-31) + live code inspection.

## Project Identity

- **Repo**: `ComfyUI-BigBunnyBall-Nodes` — public GitHub repo, portfolio piece for Tianyu's 2027 China AIGC-TA job hunt.
- **Path**: `D:\BigBunnyBall_Repo\ComfyUI-BigBunnyBall-Nodes\`
- **Language**: Python (ComfyUI custom nodes).
- **Scope**: OpenRouter API suite (LLM, image, video) + later AIGC texture QA pipeline gates (seamless_fix, delattice_fix, flipbook_qa).

## Teaching Contract (standing rules — DO NOT violate)

- Tianyu codes **unaided first**; AI reviews line-by-line like a senior afterwards.
- Stuck >20 min → **hint**, not solution. Hint escalation: concept → skeleton → near-answer.
- Quizzes/exercises use his real domain (texture maps, QA tools, AIGC pipelines).
- **Do NOT touch his ComfyUI install** — he copies files and restarts himself.
- He commits and pushes himself (standing git rule).
- Replies in English (Irish/British spelling).
- Give the rule behind the rule; he catches jargon-as-syntax sloppiness.
- When he explicitly asks to "digest" after attempting, full solutions are OK.
- **Fail loud, not soft**: raise for cannot-do-the-job (ComfyUI paints node red); try/except only for genuine recovery (first legit use: 429 retry at video stage).

## ComfyUI Node Conventions (established)

- Root `__init__.py` is the ONLY file ComfyUI requires at root — holds `NODE_CLASS_MAPPINGS` and `NODE_DISPLAY_NAME_MAPPINGS` dicts.
- Subfolder layout: `nodes/` package (empty `__init__.py` marker), one module per concern (`or_text.py`, `or_image.py`).
- Import style in root init: `from .nodes.<module> import <ClassName>`.
- Class contract: `INPUT_TYPES()` classmethod → dict with `"required"` / `"optional"` sections; `RETURN_TYPES = (tuple,)` (trailing comma!); `FUNCTION = "method_name"`; `CATEGORY = "MyOpenRouter"`.
- Widget types: `STRING` (config: `multiline`, `default`), `FLOAT`/`INT` (config: `default`, `min`, `max`, `step`), dropdown = tuple whose **first element is a list of strings** (there is NO literal `"COMBO"` token — community jargon).
- ComfyUI calls `FUNCTION` **synchronously** with kwargs; param NAMES are the contract, order is cosmetic. `async def` would return a coroutine and break the graph.
- Widget-choice philosophy: STRING for open-ended, list for enums, INT/FLOAT+bounds for numeric ranges — make invalid input impossible, not merely rejected.

## OpenRouter API (verified facts)

- **Chat**: `POST https://openrouter.ai/api/v1/chat/completions`, headers `Authorization: Bearer <key>` + `Content-Type: application/json`. Required body: `model`, `messages` (list of `{"role","content"}`). Optional: `temperature` (0–2), `max_tokens`, `seed`, `top_p`.
- **Images**: `POST https://openrouter.ai/api/v1/images`. Required: `model`, `prompt`. Optional: `aspect_ratio` (enum 1:1/16:9/9:16/4:3/3:4), `resolution` ("1K"/"2K"), `n` (1–6), `input_references` (max 4), `seed`. Response: `data[0].b64_json`, `data[0].media_type`, `usage.cost`.
- **Image refs**: `input_references` entries = `{"type":"image_url","image_url":{"url":<https URL or base64 data URL>}}`.
- **Video** (stage 4): `POST /api/v1/videos` → async job → poll `GET /api/v1/videos/{id}` until done → download `/content`.
- **Cost**: `data["usage"]["cost"]` is USD — print on every paid call (user preference from io-spark cost-spike history).
- **Reasoning models**: spend `reasoning_tokens` before writing `content`. `max_tokens=30` can blow entire budget on reasoning → `finish_reason: "length"`, `content: null`. ~3000+ tokens for a comfortable answer.
- **Response shape**: `data["choices"][0]` → `message.content`, `message.reasoning` (use `.get()`), `finish_reason`.
- Image cost ~$0.04/image at 1K, n=1. (superseded by endpoint pricing below)

### 2026-09-06 re-verification (current official docs)

- Docs moved: image guide now at `https://openrouter.ai/docs/guides/overview/multimodal/image-generation` (old `/docs/features/image-generation` 404s).
- Image endpoint request table: required = `model` + `prompt` ONLY. **No `system_prompt`/`messages` field exists on `/api/v1/images`.** (System instructions only via chat route `modalities:["text","image"]` or provider-native APIs — unpicked alternative.)
- Response: `data[0].b64_json` is the documented default ("Images are returned as base64-encoded bytes"); the field IS called `media_type` ("present whenever the format is identifiable"); `usage` reported "when available".
- **No `image_response_format` parameter exists** (that's the OpenAI images API — another agent's report conflated the two; rejected 2026-09-06).
- Other optional fields: `n` (1–10), `size` shorthand, `quality`, `output_format`, `background`, `output_compression`, `seed`, `stream` (SSE), `user`, `provider.*` routing.
- Model discovery: `GET /api/v1/images/models` + per-endpoint records (`.../models/{slug}/endpoints`).
- `qwen/qwen-image-3-pro` endpoint record: resolution {1K,2K}; aspect_ratio enum incl. 1:1/16:9/9:16/4:3/3:4 (+ extended); n 1–6; input_references 0–4; pricing $0.04 (1K output), $0.075 (2K output), $0.003 input_image.

## API Key Security Pattern (important)

- Optional `api_key` STRING widget, default `""`.
- Resolution: `widget_key or os.environ.get("OPENROUTER_API_KEY")` (rename env var from current `PERSONAL_OPENROUTER_TESTKEY` before going public).
- **Rationale**: ComfyUI saves widget values inside workflow JSON — a typed key leaks via exports/screenshots. Never commit a workflow with the widget filled. Defaults for secret widgets must be `""` (placeholder defaults like `"sk-or-..."` are truthy → always win → 401 forever).
- Session-only injection in Thonny shell: `os.environ["VAR"] = "sk-or-..."` — never in a repo file (git history remembers secrets).
- `setx` writes env vars for NEW processes only — restart Thonny/ComfyUI, not the PC.

## Python Concepts Already Taught (with the bug that taught each)

- `self`/`cls` binding; instance-vs-class call.
- Functions are objects — `f` vs `f()`.
- Positional vs keyword args; kwargs mirror ComfyUI itself.
- One-item tuples need trailing comma `("STRING",)` — bare string silently breaks the graph.
- Truthiness and the `or` idiom for defaults; empty string is falsy.
- `os.environ` / `os.environ.get()`.
- `requests.post(url, json=payload, headers=headers, timeout=N)`; `.status_code`, `.json()` (parens!), `.text`.
- Nested JSON navigation: list index `[0]`, dict index `["key"]`.
- `.get()` vs `[]` for safe fallback.
- Error philosophy: raise = ComfyUI red-node UX; try/except only for recovery.
- No async — blocking is correct in ComfyUI nodes.
- f-strings: single quotes inside f-strings for ≤3.11 compat.
- Scientific notation formatting: `f"${cost:.6f}"`.
- Widget types (STRING/FLOAT/INT/list-dropdown).
- For-loops, `list.append`, conditional dict key (for references builder).
- `Path(path).read_bytes()`, `base64.b64encode/decode`, `f.write(...)` in `"wb"` mode, `with` statement, `mkdir(exist_ok=True)` — introduced for ORImageGen.
- Context managers deep-dive: `with` guarantees close() on exception paths (try/finally sugar); analogues: C# `using`/IDisposable, TS `using`/Symbol.dispose (TS 5.2+), GDScript none needed (no exceptions + RefCounted). Files = bytes, wire = text.
- base64 two-step: `b64encode(bytes) → bytes` then `.decode()` → str for data URLs; inbound `b64decode(str) → bytes` for "wb" writes.
- Data-URL MIME label must match content (derive from suffix, fallback png).
- `[]` for contract fields vs `.get()` chains for optional metadata; cost print must never crash a node after a successful billed generation.
- Cross-agent review discipline: distinguish correctness claims (compiler/runtime decides) from style claims (judgment); check which code state each reviewer saw; verify with docs/compiler, not report confidence.

## Current Code State (updated 2026-09-06)

### `nodes/or_text.py` — two classes

**`ORTextEcho`** — DONE.
- Inputs: `text` (multiline, default "hello bigbunnyball"), `prefix` (single-line, default "router").
- Returns `(f"{prefix}: {text}",)`. FUNCTION="run_text", CATEGORY="MyOpenRouter".

**`ORTextLLM`** — WORKING (live-tested in Thonny). Outstanding housekeeping:
- Widget field named `your_api_key` — rename to `api_key` only if user asks (2026-09-06: user prefers keeping his field names).
- `max_tokens` INT: user has set default=32000, min=8000, max=64000 (exceeds handoff's "raise to 8192" note — his call, acceptable).
- Env var name `PERSONAL_OPENROUTER_TESTKEY` → rename to `OPENROUTER_API_KEY` before public.
- Response handling: content/reasoning fallback + truncation flag — implemented.
- Cost print — implemented.
- Regression tests assigned (30 tokens → reasoning+truncation flag; 3000 → clean answer) — **NOT yet confirmed run**.

### `nodes/or_image.py` — `ORImageGen` COMPLETE (built + reviewed 2026-09-06)

- `INPUT_TYPES` required: `user_prompt` (multiline), `model` (default "qwen/qwen-image-3-pro"), `aspect_ratio` dropdown (1:1/16:9/9:16/4:3/3:4, default 16:9), `output_resolution` dropdown (1K/2K, default 1K).
- `INPUT_TYPES` optional: `your_api_key` (default ""), `image_1..4` (each accepts https URL or local path, default "").
- `to_data_url` is an instance method (`self` present). MIME label derived from `Path(ref).suffix.lower()` via ext_map (jpg/jpeg/webp), fallback png.
- run_main: key guard (raise if missing) → headers → references loop (non-empty → data URL via to_data_url) → payload (`"prompt": user_prompt`, `"resolution": output_resolution` + conditional `input_references`) → POST timeout 180 → status guard (raise with response.text) → unpack (`data["data"][0]["b64_json"]`, ext via `first.get("media_type","image/png")`) → save `test_outputs/generated.{ext}` ("wb") → cost print defensive: `data.get("usage", {}).get("cost", "n/a")` → `return (str(out_path),)`.
- `RETURN_TYPES = ("STRING",)`, `FUNCTION = "run_main"`, `CATEGORY = "MyOpenRouter"`.
- **User naming decisions are FINAL (2026-09-06):** keep `user_prompt`, `output_resolution`, `your_api_key`, `image_N` as-is. Do not suggest renames.
- Pending: Thonny smoke tests + paid test runs (1K text-to-image ~$0.04, then local-PNG ref run ~$0.043).

### Root `__init__.py`
- Registers all three nodes (2026-09-06): `ORTextEcho`, `ORTextLLM`, `ORImageGen`.
- Display names (user's): "OpenRouter Text Echo", "OpenRouter Text LLM", "OpenRouter Image Generation".

### `test_script_thonny.py`
- Personal Thonny scratch file (currently has an ORTextLLM live test).
- **Must be added to .gitignore** — contains env var name.

### `.gitignore`
- Generic Python gitignore (from GitHub template).
- **Pending additions**: `test_script_thonny.py`, `test_outputs/`.

### `README.md` / `LICENSE`
- README is a one-line pitch; needs real install/usage docs.
- LICENSE exists (initial commit).

## Roadmap (ordered)

1. ~~**Finish ORImageGen**~~ — DONE (2026-09-06). Thonny smoke tests + paid test runs next.
2. **In-graph ComfyUI smoke test**: copy folder to custom_nodes, restart, wire all three nodes, run. Likely blocker: `ModuleNotFoundError: requests` in ComfyUI's embedded Python → fix with embedded-pip install. Screenshot empty-key field running graph as first README asset. **Adopt `folder_paths.get_output_directory()` absolute output here** (deferred from 2026-09-06 review: the folder_paths import breaks Thonny tests).
3. **Git ceremony**: `requirements.txt` (one line: `requests`); .gitignore += `test_script_thonny.py`, `test_outputs/`; README install/usage docs; user commits+pushes.
4. **Housekeeping (only if user asks)**: env var rename `PERSONAL_OPENROUTER_TESTKEY` → `OPENROUTER_API_KEY` before public. Widget field names stay as user wrote them (2026-09-06 decision).
5. **Stage 3 v2**: IMAGE tensor output (proper ComfyUI image socket) instead of path string.
6. **Stage 4**: video models (async job + polling; 429 retry-with-backoff = first legit try/except).
7. **Later**: wrap TE QA tools (seamless_fix, delattice_fix, flipbook_qa) as QA-gate nodes.

## ComfyUI Install Path (unverified)

- `D:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\...` (exact custom_nodes path not yet confirmed — user copies files himself per teaching contract).
- Embedded Python pip: `python_embeded\python.exe -m pip install requests`.

## User Preferences Observed

- Wants cost printed on every paid call.
- Prefers understanding WHY — answer with the rule behind the rule.
- Fine with being given full solutions when he asks to "digest", but only after attempting.
- Codes in Thonny first (instant smoke tests without ComfyUI restart) — good pattern, encourage it.
