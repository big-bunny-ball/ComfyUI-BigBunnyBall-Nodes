# Project Memory — ComfyUI-BigBunnyBall-Nodes

> Durable project state for this ComfyUI custom-nodes pack. Maintained by Hanako (since 2026-09-06).
> Ingested from handoff doc `comfyui-node-tutoring-session.md` (2026-08-31) + live code inspection.
> 2026-09-06 evening: stdlib urllib rewrite (zero deps), CategoryList registry, folder_paths output, loader-verified imports.
> 2026-09-12: IMAGE tensor I/O milestone — ORImageGen tensor output + 4 tensor reference inputs (path widgets removed by user decision); ORTextLLM vision (6 optional IMAGE inputs). Pre-flight verified via loader sim + intercepted HTTP, zero credits.

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
- **Pack-internal imports must be RELATIVE** (`from .catogory_list import ...`). Absolute `from nodes.x import` works in Thonny (repo root on sys.path) but dies under ComfyUI's importlib loader — verified 2026-09-06 by loader simulation: `ModuleNotFoundError: No module named 'nodes'`.
- Class contract: `INPUT_TYPES()` classmethod → dict with `"required"` / `"optional"` sections; `RETURN_TYPES = (tuple,)` (trailing comma!); `FUNCTION = "method_name"`; `CATEGORY = CategoryList.api_openrouter()` → `"API-OpenRouter"` (was `"MyOpenRouter"`).
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
- `requests` IS in current ComfyUI core requirements.txt (verified) — but pack now uses stdlib `urllib` anyway → zero third-party deps; `requirements.txt` unnecessary.

### 2026-09-12 verification: chat vision inputs (image understanding)

- Docs: `https://openrouter.ai/docs/guides/overview/multimodal/image-understanding`.
- Vision goes through `/api/v1/chat/completions` with a **multi-part `messages` content array**: `{"type":"text","text":...}` + `{"type":"image_url","image_url":{"url":...}}` entries. Same `image_url` shape as the images endpoint's `input_references`.
- `url` accepts a public https URL **or** a base64 data URL. Supported content types: `image/png`, `image/jpeg`, `image/webp`, `image/gif`.
- **Docs explicitly recommend text part FIRST, then images** (parsing order); if images must lead, put them in the system prompt.
- Max images per request varies per provider/model — no universal cap.
- Vision requires a vision-capable model; `qwen/qwen3.7-flash` (ORTextLLM's default) NOT verified for image support — if unsupported, the provider 4xx surfaces via the HTTPError guard (fail-loud).
- Image input tokens are billed (~$0.003/input image on the qwen endpoint family) → shows in the cost print.

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
- urllib HTTP: `urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=..., method="POST")` + `urlopen(req, timeout=N)`; non-200 raises `urllib.error.HTTPError` (`.code`, `.read()`) → catch and re-raise loudly. `import urllib.request` explicitly (submodules not auto-imported). SSL via system store, no certifi.
- Absolute vs relative imports under importlib loaders; the cwd-on-sys.path illusion; loader-simulation pre-flight (spec_from_file_location + module_from_spec + exec_module).
- Category registry pattern (single source of truth for CATEGORY strings); type annotations (`: str`, `-> str`).
- ComfyUI IMAGE contract: torch tensor `(B, H, W, C)` channels-LAST, float32, values 0–1; B = batch (single image = batch of 1); `.convert("RGB")` enforces C=3.
- b64 → tensor chain: `b64decode` → `io.BytesIO` (in-memory file-like, duck-typed like `open()`) → `Image.open().convert("RGB")` → `np.array().astype("float32") / 255.0` → `torch.from_numpy().unsqueeze(0)`. **astype BEFORE divide** — dividing uint8 first promotes to float64 (off-contract, VAE rejects).
- Reverse chain (tensor → data URL): `tensor[0]` drops batch dim → `* 255` + `astype("uint8")` → PIL `save(buf, format="PNG")` → b64 data URL. MIME hardcoded is CORRECT here (we chose the format; label can't lie). NOTE: this supersedes the old derive-MIME-from-suffix lesson — `to_data_url` (local-file refs) was deleted 2026-09-12 when inputs became tensors.
- `torch.from_numpy` shares the numpy buffer (no copy). `bool()` of a multi-element tensor is ambiguous (PyTorch raises/warns) → optional tensor inputs must be guarded with `is not None`, never truthiness.
- Optional INPUT_TYPES entries are passed as kwargs ONLY when wired → matching `=None` defaults on the FUNCTION signature, or unwired calls TypeError.
- `RETURN_TYPES` order is POSITIONAL (maps to sockets); `RETURN_NAMES` labels the pins.
- OpenRouter chat multipart content: conditional list-vs-string `content` (text part first) — same conditional-payload pattern as `input_references`.
- Case-sensitivity trap: `from PIL import image` (lowercase) raises ImportError even on case-insensitive Windows — Pillow lazy-loads names case-sensitively through `__all__`. Kills the WHOLE pack at import (all nodes vanish), same failure class as the absolute-import landmine.
- Intercepted-HTTP functional testing: monkeypatch `urllib.request.Request`/`urlopen` in a loader-sim harness → call the real `run_main` with fake keys/fake tensors, capture and assert the exact JSON payload. Proves branch logic (multipart vs plain, refs vs no refs) with zero network and zero credits. Harnesses live in agent workspace scratch, NOT the repo.

## Current Code State (updated 2026-09-12)

### `nodes/or_text.py` — two classes

**`ORTextEcho`** — DONE.
- Inputs: `text` (multiline, default "hello bigbunnyball"), `prefix` (single-line, default "router").
- Returns `(f"{prefix}: {text}",)`. FUNCTION="run_text", CATEGORY via CategoryList = "API-OpenRouter".

**`ORTextLLM`** — WORKING (live-tested in Thonny). Outstanding housekeeping:
- Rewritten to stdlib urllib (2026-09-06); cost print uses `data["usage"]["cost"]` (`[]` is fine for chat — usage always present on chat endpoint).
- Widget field named `your_api_key` — rename to `api_key` only if user asks (2026-09-06: user prefers keeping his field names).
- `max_tokens` INT: user has set default=32000, min=8000, max=64000 (exceeds handoff's "raise to 8192" note — his call, acceptable).
- Env var name `PERSONAL_OPENROUTER_TESTKEY` → rename to `OPENROUTER_API_KEY` before public.
- Response handling: content/reasoning fallback + truncation flag — implemented.
- Cost print — implemented.
- Regression tests assigned (30 tokens → reasoning+truncation flag; 3000 → clean answer) — **NOT yet confirmed run** (user now prefers in-graph testing).
- **Vision inputs (2026-09-12, user-requested build):** six optional `image_1..6` IMAGE tensor inputs (`=None` defaults on run_main); new helper `tensor_to_data_url` (PNG data URL); when any image wired, user message content becomes multipart list `[{"type":"text",...}, {"type":"image_url","image_url":{"url":...}}, ...]` (text FIRST per docs), else stays plain string — original text-only behaviour untouched. Functional-tested via intercepted HTTP (parts/text-first/plain-string branches all verified). NOT yet tested in-graph; needs a vision-capable model set in the widget.

### `nodes/or_image.py` — `ORImageGen` COMPLETE + TENSOR UPGRADE BUILT (2026-09-12, pending in-graph test)

- `INPUT_TYPES` required: `user_prompt` (multiline), `model` (default "qwen/qwen-image-3-pro"), `aspect_ratio` dropdown (1:1/16:9/9:16/4:3/3:4, default 16:9), `output_resolution` dropdown (1K/2K, default 1K).
- `INPUT_TYPES` optional: `your_api_key` (default ""), `image_1..4` — **now IMAGE tensor sockets** (2026-09-12, user decision: tensors ONLY, no local paths/URLs; old STRING path widgets deleted along with `to_data_url` and its ext_map MIME logic). `run_main` has `image_1=None..image_4=None` defaults; loop guard is `is not None` (never truthiness on tensors).
- `tensor_to_data_url` (instance method): `tensor[0]` → `*255`+`astype("uint8")` → PNG into BytesIO → `data:image/png;base64,...`. Sends FIRST FRAME ONLY of B>1 batches — deliberate simplification (LoadImage is B=1).
- run_main: key guard (raise if missing) → headers → references loop (wired tensors → data URL) → payload (`"prompt": user_prompt`, `"resolution": output_resolution` + conditional `input_references`) → POST via urllib timeout 180 → HTTPError catch-and-reraise (raise with body) → unpack (`data["data"][0]["b64_json"]`, ext via `first.get("media_type","image/png")`) → save `ComfyUI/output/or_images/generated.{ext}` via `folder_paths.get_output_directory()` ("wb") → cost print defensive: `data.get("usage", {}).get("cost", "n/a")`.
- **TENSOR OUTPUT (2026-09-12):** `image_to_tensor(b64_string)` helper (BytesIO → `Image.open().convert("RGB")` → `astype("float32")/255.0` → `from_numpy().unsqueeze(0)` → `(1,H,W,3)`); `RETURN_TYPES = ("IMAGE", "STRING")`, `RETURN_NAMES = ("image", "path")`, returns `(image_tensor, str(out_path),)` — tensor first, positional. `FUNCTION = "run_main"`, `CATEGORY` via CategoryList = "API-OpenRouter". Disk save KEPT for now (possible dup with downstream SaveImage — user's author call later).
- **User naming decisions are FINAL (2026-09-06):** keep `user_prompt`, `output_resolution`, `your_api_key`, `image_N` as-is. Do not suggest renames.
- New top imports (2026-09-12): `io`, `numpy as np`, `torch`, `from PIL import Image` (CAPITAL I — lowercase import kills the whole pack, Pillow lazy-loader is case-sensitive). All exist in ComfyUI embedded Python. File remains ComfyUI-only (folder_paths) — accepted trade.
- **Verified 2026-09-12 pre-flight (loader sim + intercepted HTTP, zero credits):** pack loads; INPUT_TYPES image_1..4 all IMAGE; t2i branch omits `input_references`; i2i branch sends N refs with per-tensor pixels intact; returns 2-tuple; output file written. **NOT yet verified in-graph with a real paid run.**
- v1 in-graph history (2026-09-06, path-string era): t2i (70.4s) and i2i (local-path ref) both succeeded. Outputs land in `C:\Users\Tianyu He\ComfyUI-Shared\output\or_images\`. Known friction: fixed filename `generated.png` overwrites every run — timestamp fix offered 2026-09-06, **DECLINED by user 2026-09-12** (do not re-offer unless asked).

### `nodes/catogory_list.py` — CategoryList registry (NEW 2026-09-06)

- Single source of truth for category names; `CategoryList.api_openrouter()` → "API-OpenRouter".
- Method has no `self` (called on the class); `@staticmethod` suggested as the honest label. `__init__` = pass (dead attributes removed by user).
- Filename typo "catogory_list" — git mv candidate (class name is correctly spelled).
- Imported RELATIVELY from or_text.py / or_image.py.
- NOTE (2026-09-12): `tensor_to_data_url` is duplicated verbatim in or_text.py and or_image.py — flagged to user; DRY candidate for a future `nodes/utils.py` (or broadened registry module) when a third node needs it. Not done — user's call.

### Root `__init__.py`
- Registers all three nodes (2026-09-06): `ORTextEcho`, `ORTextLLM`, `ORImageGen`.
- Display names (user's): "OpenRouter Text Echo", "OpenRouter Text LLM", "OpenRouter Image Generation".

### `test_script_thonny.py`
- Personal Thonny scratch file (currently has an ORTextLLM live test).
- **Must be added to .gitignore** — contains env var name.

### `.gitignore`
- Generic Python gitignore (from GitHub template).
- Added by user (2026-09-06): `test_script_thonny.py`, `PROJECT_MEMORY.md`. NOTE: PROJECT_MEMORY.md is already tracked, so the ignore line has no effect until `git rm --cached` (user's call — the doc holds no secrets; keeping it tracked is fine).
- No `test_outputs/` entry needed — images now go to `ComfyUI/output/or_images/`.

### `README.md` / `LICENSE`
- README is a one-line pitch; needs real install/usage docs.
- LICENSE exists (initial commit).

## Roadmap (ordered)

1. ~~**Finish ORImageGen**~~ — DONE. **In-graph verified 2026-09-06**: t2i + i2i both succeed (first paid runs in ComfyUI).
2. **In-graph ComfyUI smoke test** — DONE for function (2026-09-06); remaining: screenshot empty-key red node as first README asset.
3. **Git ceremony**: `requirements.txt` NO LONGER NEEDED (zero deps after urllib rewrite); README install/usage docs; user commits+pushes. Commits so far: 3aaf432 (ORImageGen v1), 2f46830 (urllib+registry), + 2026-09-12 tensor I/O commit (title/body supplied).
4. **Housekeeping (only if user asks)**: env var rename `PERSONAL_OPENROUTER_TESTKEY` → `OPENROUTER_API_KEY` before public. Widget field names stay as user wrote them (2026-09-06 decision).
5. ~~**Stage 3 v2**: IMAGE tensor output~~ — BUILT 2026-09-12 (tensor out + tensor refs in + ORTextLLM vision), pre-flight verified; **remaining: in-graph paid test** — ORImageGen→PreviewImage, LoadImage→ORTextLLM (vision-capable model!), ORImageGen→ORImageGen i2i chain. Timestamp filename fix DECLINED by user (2026-09-12) — don't re-offer.
6. **Stage 4**: video models (async job + polling; 429 retry-with-backoff = first legit try/except).
7. **Later**: wrap TE QA tools (seamless_fix, delattice_fix, flipbook_qa) as QA-gate nodes; possible `nodes/utils.py` for the duplicated `tensor_to_data_url`.

## ComfyUI Install Path (verified 2026-09-06)

- custom_nodes: `E:\Comfyui Installs\ComfyUI\ComfyUI\custom_nodes` (user-provided).
- Actual output dir resolves to `C:\Users\Tianyu He\ComfyUI-Shared\output\` (shared output configured) — images under `or_images\`.
- Embedded Python lives under the same tree; no pip installs needed — the pack has zero third-party deps.

## User Preferences Observed

- Wants cost printed on every paid call.
- Prefers understanding WHY — answer with the rule behind the rule.
- Fine with being given full solutions when he asks to "digest", but only after attempting.
- Codes in Thonny first for free smoke tests (class introspection, no paid calls); paid calls go in-graph to save API credits (2026-09-06).
- Wants copy-pasteable commit title/body for GitHub Desktop commits.
- **Prefers COMPACT step-by-step guides over long concept essays** (2026-09-12: "its too massive... can you just give me step by step script guide&explanation?") — numbered steps, minimal code, one-line whys.
- Sometimes asks the AI to implement directly ("please check... and make sure X can also take image tensor") — direct-build requests override code-unaided-first for that specific feature; still explain changes after.
- **Tensor sockets over file-path widgets** (2026-09-12, explicit: "I dont want the local file path. I just want image tensor inputs") — graph-native wiring is his design direction.
- Declined the timestamped-filename fix (2026-09-12) — accepts `generated.png` overwrite behaviour; do not re-offer.
