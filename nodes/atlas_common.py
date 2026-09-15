"""Shared plumbing for the Atlas Cloud video nodes.

Atlas Cloud is an ASYNC provider: a POST creates a prediction, then the
prediction id is polled until it reaches a terminal state, then the finished
video is downloaded from the URL in `outputs[0]`.

Money rule baked through this module: once a prediction id exists, a render has
been paid for. Every failure path after submit reports the id so the render can
be re-fetched instead of re-bought.

ComfyUI-only (folder_paths / comfy_api / comfy.utils) — same trade as or_image.py.
Zero third-party deps: stdlib urllib only, plus ComfyUI's own PyAV via VideoFromFile.
"""

import base64
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

import folder_paths
from comfy_api.latest import VideoFromFile

ATLAS_BASE = "https://api.atlascloud.ai/api/v1/model"
GENERATE_URL = f"{ATLAS_BASE}/generateVideo"
PREDICTION_URL = f"{ATLAS_BASE}/prediction"
UPLOAD_URL = f"{ATLAS_BASE}/uploadMedia"

# HTTP statuses worth retrying. 429 = rate limited, 5xx = provider side.
RETRYABLE = {429, 500, 502, 503, 504}
# Narrower set for the SUBMIT call: a 500 may have already created a billed job,
# so re-POSTing could double-charge. Gateway-level codes are safe (request never
# reached the model), and so is 429 (rejected before any job existed).
SUBMIT_RETRYABLE = {429, 502, 503, 504}

# Terminal prediction states.
DONE_STATES = {"completed", "succeeded", "success"}
FAILED_STATES = {"failed", "error"}
# Cancelled/expired never come back — learned the hard way in the Spark pipeline:
# treating them as "still running" wedges the node until timeout.
DEAD_STATES = {"cancelled", "canceled", "expired", "timeout"}

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}


# ---------------------------------------------------------------- keys / HTTP

def resolve_api_key(widget_key: str) -> str:
    """Widget wins, then the environment. Two env names are accepted: the one in
    Atlas's own curl examples, and the one used by the Spark pipeline's .env."""
    key = (widget_key or "").strip()
    if not key:
        key = (os.environ.get("ATLASCLOUD_API_KEY")
               or os.environ.get("ATLAS_CLOUD") or "").strip()
    if not key:
        raise Exception(
            "No Atlas Cloud API key: fill the your_api_key widget, or set the "
            "ATLASCLOUD_API_KEY environment variable (ATLAS_CLOUD also works). "
            "Remember setx only affects newly started processes — restart ComfyUI."
        )
    return key


def _auth_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


class _Response:
    """Minimal response wrapper: status + raw body text."""

    def __init__(self, status: int, text: str):
        self.status = status
        self.text = text

    def json(self):
        return json.loads(self.text)


def _do_request(req: urllib.request.Request, timeout: int) -> _Response:
    """One request. Non-2xx arrives as urllib.error.HTTPError (urllib raises
    instead of returning a status, unlike requests) — converted into _Response so
    callers can decide between retrying and failing loudly."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _Response(resp.status, resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return _Response(err.code, body)


def request_with_retry(req: urllib.request.Request, *, timeout: int, retryable: set,
                       label: str, attempts: int = 4) -> _Response:
    """Run a request, backing off on transient failures.

    This is the pack's FIRST legitimate try/except: a 429 is recoverable, so we
    retry instead of painting the node red. Anything not retryable is raised
    immediately with the provider's own body — fail loud, not soft.
    """
    delay = 2.0
    last = None
    for i in range(attempts):
        resp = _do_request(req, timeout)
        if resp.status < 400:
            return resp
        last = resp
        if resp.status not in retryable:
            raise Exception(f"{label} failed ({resp.status}): {resp.text[:2000]}")
        if i < attempts - 1:
            print(f"[atlas] {label}: HTTP {resp.status}, retrying in {delay:.0f}s "
                  f"(attempt {i + 1}/{attempts})")
            time.sleep(delay)
            delay = min(delay * 2, 20.0)
    raise Exception(f"{label} failed after {attempts} attempts "
                    f"(last HTTP {last.status}): {last.text[:2000]}")


def _get_json(url: str, api_key: str, *, timeout: int = 60, label: str = "request") -> dict:
    req = urllib.request.Request(url, headers=_auth_headers(api_key), method="GET")
    return request_with_retry(req, timeout=timeout, retryable=RETRYABLE, label=label).json()


# ------------------------------------------------------------ image plumbing

def _frame_array(tensor) -> np.ndarray:
    """tensor -> a plain (H, W, 3) uint8-range float array.

    Defensive on purpose: `tensor[0]` is normally the first frame of a (B,H,W,C)
    IMAGE tensor, but a stray extra dim (or a 2-D mask) would otherwise surface as
    PIL's cryptic "Cannot handle this data type: (1, 1, 1920, 3)". Squeezing
    singleton dims handles the harmless cases; anything else fails loudly with a
    message that says what was actually received.
    """
    frame = tensor[0]
    arr = frame.numpy() if hasattr(frame, "numpy") else np.asarray(frame)
    if arr.ndim == 4:                      # tensor[0] handed back a whole batch
        arr = arr[0]
    arr = np.squeeze(arr)
    if arr.ndim == 2:                      # grayscale -> RGB
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    if arr.ndim != 3 or arr.shape[2] not in (3, 4):
        raise Exception(
            f"Expected an IMAGE tensor of shape (B, H, W, 3); got {arr.shape}. "
            "Wire a real IMAGE output into this input."
        )
    return arr


def encode_frame(tensor, *, max_bytes: int, max_edge: int = 0,
                 label: str = "frame") -> tuple:
    """IMAGE tensor -> (raw_bytes, mime) sized to survive the wire.

    Lossless PNG first (this is a FIRST FRAME, quality matters), then progressive
    fallbacks: JPEG q92, then downscale. Hard-won lesson from the Spark pipeline:
    base64 inflates the body by 33% and oversized payloads die at the proxy AFTER
    the render was billed. Returning early beats failing late.

    tensor[0] takes frame 0 of a batch — deliberate simplification, consistent with
    the rest of this pack.
    """
    arr = _frame_array(tensor)
    img = Image.fromarray((arr * 255.0).astype("uint8")).convert("RGB")

    if max_edge and max(img.size) > max_edge:
        scale = max_edge / float(max(img.size))
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                         Image.LANCZOS)

    def to_png(im):
        b = io.BytesIO()
        im.save(b, format="PNG")
        return b.getvalue()

    def to_jpeg(im, quality):
        b = io.BytesIO()
        im.save(b, format="JPEG", quality=quality)
        return b.getvalue()

    raw = to_png(img)
    if len(raw) <= max_bytes:
        return raw, "image/png"

    raw = to_jpeg(img, 92)
    if len(raw) <= max_bytes:
        return raw, "image/jpeg"

    shrunk = img
    for _ in range(6):
        shrunk = shrunk.resize((max(1, int(shrunk.width * 0.85)),
                                max(1, int(shrunk.height * 0.85))), Image.LANCZOS)
        raw = to_jpeg(shrunk, 90)
        if len(raw) <= max_bytes:
            return raw, "image/jpeg"

    raise Exception(
        f"{label} could not be encoded under {max_bytes / 1e6:.0f} MB even after "
        f"downscaling to {shrunk.width}x{shrunk.height}. Use a smaller source image."
    )


def bytes_to_data_url(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def check_frame_limits(tensor, label: str, *, min_edge: int = 0,
                       max_ratio: float = 0.0) -> None:
    """Pre-flight the DOCUMENTED Atlas frame limits before paying for a job.
    Only enforced where the docs state a limit (wan). 0 = do not check.

    Reads the real pixel array rather than tensor.shape, so it stays correct for
    any batch depth."""
    if not (min_edge or max_ratio):
        return
    arr = _frame_array(tensor)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if min_edge and min(h, w) < min_edge:
        raise Exception(
            f"{label} is {w}x{h}; Atlas requires every edge >= {min_edge}px for this "
            "model. Upscale the frame first."
        )
    if max_ratio:
        ratio = max(h, w) / max(1, min(h, w))
        if ratio > max_ratio:
            raise Exception(
                f"{label} aspect ratio is {ratio:.1f}:1; this model allows at most "
                f"{max_ratio:.0f}:1."
            )


def upload_media(raw: bytes, mime: str, api_key: str, *, filename: str = "frame.png") -> str:
    """POST multipart/form-data to /uploadMedia, return the public download_url.

    Needed because wan's `image` / `last_image` accept a PUBLIC URL ONLY, while
    minimax h3 accepts "Public URL or Base64" and can skip this hop entirely.
    """
    boundary = f"----BigBunnyBall{uuid.uuid4().hex}"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        raw,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    data = request_with_retry(req, timeout=180, retryable=RETRYABLE,
                              label="frame upload").json()
    url = _dig(data, "download_url") or _dig(data, "url")
    if not url:
        raise Exception(f"Atlas upload returned no download URL: {json.dumps(data)[:800]}")
    return url


def _dig(data, key):
    """Find a key in a possibly-nested {'code':200,'data':{...}} envelope."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    inner = data.get("data")
    if isinstance(inner, dict) and key in inner:
        return inner[key]
    return None


# ------------------------------------------------------- submit / poll / save

def submit_prediction(payload: dict, api_key: str) -> str:
    """Start the job. Returns the prediction id — from this moment we are billed."""
    req = urllib.request.Request(
        GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )
    data = request_with_retry(req, timeout=120, retryable=SUBMIT_RETRYABLE,
                              label="video submit").json()
    pid = _dig(data, "id") or _dig(data, "prediction_id")
    if not pid:
        raise Exception(f"Atlas submit returned no prediction id: {json.dumps(data)[:800]}")
    return str(pid)


def extract_video_url(data) -> str:
    """outputs[0] is normally a plain URL string; tolerate a dict shape too."""
    outputs = _dig(data, "outputs")
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in ("url", "video_url", "output", "download_url", "src"):
                if first.get(key):
                    return str(first[key])
    for key in ("video_url", "url", "output"):
        found = _dig(data, key)
        if isinstance(found, str) and found:
            return found
    raise Exception(f"Atlas reported success but returned no video URL: {json.dumps(data)[:800]}")


def poll_prediction(prediction_id: str, api_key: str, *, timeout_minutes: int,
                    interval: float = 5.0, progress=None) -> dict:
    """Block until the prediction is terminal, then return its data dict.

    ComfyUI calls nodes synchronously, so blocking IS the correct shape here —
    the queue simply waits, exactly like a long sampling run.

    Every failure path after this point names the prediction id, because a
    submitted render is already paid for and must stay recoverable.
    """
    deadline = time.monotonic() + max(1, timeout_minutes) * 60
    started = time.monotonic()
    polls = 0
    while True:
        data = _get_json(f"{PREDICTION_URL}/{urllib.parse.quote(prediction_id)}",
                         api_key, label=f"poll {prediction_id}")
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        status = str(payload.get("status") or "").lower()
        polls += 1

        if status in DONE_STATES:
            return payload
        if status in FAILED_STATES:
            err = payload.get("error") or "no error detail returned"
            raise Exception(f"Video generation FAILED (prediction {prediction_id}): {err}")
        if status in DEAD_STATES:
            raise Exception(f"Video generation was '{status}' (prediction {prediction_id}). "
                            "This state is terminal — it will not resume.")

        if time.monotonic() > deadline:
            raise Exception(
                f"Timed out after {timeout_minutes} min waiting for prediction "
                f"{prediction_id} (last status: '{status or 'unknown'}'). "
                "THE RENDER MAY STILL BE RUNNING AND IS ALREADY PAID FOR — do not "
                "re-run blindly; check the prediction id on the Atlas dashboard."
            )

        if progress is not None:
            progress(status, time.monotonic() - started)
        time.sleep(interval)


def download_and_save(video_url: str, filename_prefix: str) -> tuple:
    """Download the finished video into ComfyUI's output folder and wrap it as a
    native VIDEO container.

    Returns (video_container, absolute_path, saved_filename, subfolder) — the last
    two are what the canvas preview needs to locate the file.

    Uses folder_paths.get_save_image_path so files get an auto-incrementing
    counter (or_videos_00001_.mp4) — the same mechanism core SaveVideo uses.
    Nothing is ever overwritten, so a paid render can't be clobbered by the next
    run, and no timestamps are needed.
    """
    raw = _download(video_url)

    # Dimensions are only needed to compute the save path, and probing can
    # fail on an unusual container — so it must never stand between the download
    # and the disk write. A paid render lands on disk FIRST, always.
    width, height = 0, 0
    bytes_probe_ok = False
    try:
        probe = VideoFromFile(io.BytesIO(raw))
        width, height = (int(v) for v in probe.get_dimensions())
        bytes_probe_ok = True
    except Exception as err:
        print(f"[atlas] could not probe dimensions before saving ({err}); "
              "saving anyway")

    full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        filename_prefix, folder_paths.get_output_directory(), width, height)
    Path(full_folder).mkdir(parents=True, exist_ok=True)

    ext = _guess_ext(video_url)
    saved_name = f"{filename}_{counter:05d}_{ext}"
    out_path = Path(full_folder) / saved_name
    with open(out_path, "wb") as f:
        f.write(raw)
    print(f"[atlas] saved {out_path} ({len(raw) / 1e6:.2f} MB)")

    # Build the VIDEO container from the file we just committed. VideoFromFile is
    # lazy (it does not validate on construction), so probe it explicitly: a node
    # that returns an undecodable container would report success and then fail in
    # some downstream node, far from the cause. Fail loud HERE, naming the path,
    # because the bytes are already safe on disk.
    container = VideoFromFile(str(out_path))
    try:
        dims = container.get_dimensions()
        width, height = (int(v) for v in dims)
        print(f"[atlas] {width}x{height}, {float(container.get_duration()):.1f}s")
    except Exception as err:
        if bytes_probe_ok:
            # decoded fine from memory but not from the file — still usable bytes,
            # so report rather than discard
            print(f"[atlas] warning: file probe failed ({err}); "
                  "the in-memory decode succeeded, continuing")
        else:
            raise Exception(
                f"Atlas returned {len(raw)} bytes that are not a decodable video "
                f"({err}). The bytes are saved and recoverable at: {out_path}. "
                "Do NOT re-run blindly — the render was billed; open that file or "
                "check the prediction on the Atlas dashboard first."
            ) from None

    return container, str(out_path), saved_name, subfolder


def preview_video_ui(filename: str, subfolder: str) -> dict:
    """The `ui` payload that makes the clip show up in ComfyUI's viewer.

    Verified shape: core PreviewVideo serialises to
    {"images": [{"filename","subfolder","type"}], "animated": [true]} — the
    frontend plays any entry with animated=true as a video.
    """
    return {
        "images": [{
            "filename": filename,
            "subfolder": subfolder,
            "type": "output",
        }],
        "animated": (True,),
    }


def _download(url: str, *, attempts: int = 4) -> bytes:
    """GET the video bytes. Idempotent, so any transient error is retryable."""
    delay = 2.0
    last_err = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "ComfyUI-BigBunnyBall-Nodes/1.0"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code not in RETRYABLE:
                raise Exception(f"Video download failed ({err.code}): {err.reason}") from None
            last_err = err
        except Exception as err:      # network reset / timeout mid-stream
            last_err = err
        if i < attempts - 1:
            print(f"[atlas] video download retrying in {delay:.0f}s ({i + 1}/{attempts})")
            time.sleep(delay)
            delay = min(delay * 2, 20.0)
    raise Exception(f"Video download failed after {attempts} attempts: {last_err}")


def _guess_ext(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    ext = Path(path).suffix.lower()
    return ext if ext in VIDEO_EXTS else ".mp4"


# ------------------------------------------------------------------- logging

def report_cost(data: dict, model: str, prediction_id: str, elapsed: float) -> None:
    """Print the run summary. Cost is optional metadata — a missing field must
    never crash a node that has already produced a billed video."""
    cost = None
    for key in ("cost", "total_cost", "price"):
        found = _dig(data, key)
        if isinstance(found, (int, float)):
            cost = found
            break
    usage = _dig(data, "usage")
    if cost is None and isinstance(usage, dict):
        for key in ("cost", "total_cost"):
            if isinstance(usage.get(key), (int, float)):
                cost = usage[key]
                break
    cost_str = f"${cost:.6f}" if isinstance(cost, (int, float)) else "n/a (not reported)"
    print(f"[atlas] model={model} | prediction={prediction_id} | "
          f"time={elapsed:.1f}s | cost: {cost_str}")


def make_progress_bar(node_id):
    """Optional progress bar so a multi-minute poll doesn't look frozen.
    Wrapped in try/except because it is pure UX: if ComfyUI ever changes this API,
    the render must still succeed. Returns None when unavailable."""
    try:
        from comfy.utils import ProgressBar
        return ProgressBar(100, node_id=node_id)
    except Exception:
        return None
