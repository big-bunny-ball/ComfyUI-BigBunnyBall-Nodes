"""Atlas Cloud video generation nodes (MiniMax H3 Max + Alibaba Wan 3.0).

Atlas Cloud is ASYNC, unlike OpenRouter's image endpoint: a POST creates a
prediction, the prediction id is polled until terminal, then the finished video
is downloaded from the URL in `outputs[0]`. ComfyUI calls nodes synchronously,
so blocking in the poll loop is the correct shape — the queue waits, exactly as
it does for a long sampling run.

Design decisions worth knowing:

- OUTPUT is a real VIDEO socket (ComfyUI >= 0.35 has a native VIDEO type, proven
  against this install: SaveVideo / LoadVideo / GetVideoComponents all use the
  string "VIDEO"). So the clip plugs straight into SaveVideo, VideoSlice,
  GetVideoComponents — no path-string workaround. The raw Atlas URL and the local
  path are still exposed as STRING outputs.
- Money rule: once a prediction id exists, the render is billed. Every failure
  path after submit names that id, so a finished render is re-fetched rather than
  re-bought. The id is printed to the console the instant it comes back.
- minimax h3 `image`/`end_image` accept "Public URL or Base64" -> frames go in as
  data URLs, no upload hop. wan `image`/`last_image` accept a PUBLIC URL ONLY ->
  frames are uploaded to /uploadMedia first and the returned URL is used. That
  asymmetry is documented by Atlas and is the main difference between the two
  node families.
- 429/5xx get retried with backoff (the pack's first legitimate try/except);
  everything else raises loudly so ComfyUI paints the node red.

ComfyUI-only (folder_paths / comfy_api / comfy.utils). Zero third-party deps:
stdlib urllib + Pillow/numpy, both already in ComfyUI core.
"""

import time

from .catogory_list import CategoryList
from .atlas_common import (
    bytes_to_data_url,
    check_frame_limits,
    download_and_save,
    encode_frame,
    extract_video_url,
    make_progress_bar,
    poll_prediction,
    preview_video_ui,
    report_cost,
    resolve_api_key,
    submit_prediction,
    upload_media,
)

POLL_INTERVAL = 5.0          # seconds between polls

# Body budgets. base64 inflates by ~33%, and oversized payloads die at the proxy
# AFTER the render is billed — so frames are encoded to fit, never sent raw.
H3_MAX_FRAME_BYTES = 9_000_000     # -> ~12 MB of base64 inside the JSON body
WAN_MAX_FRAME_BYTES = 18_000_000   # documented Atlas limit is 20 MB

# Resolution enums — EXACTLY as specified by Tianyu (2026-09-13). Atlas's live
# schema also offers SR/ESR upscale tiers (1440p-sr, 4k-sr, 720p-esr, ...); those
# are DELIBERATELY EXCLUDED — they cost far more and Tianyu does not want them
# one click away. Do not re-add without being asked.
# wan note: 1080p is listed because it is Tianyu's own stated DEFAULT, so it must
# be selectable; 480p/720p are his stated options.
H3_RESOLUTIONS = ["480P", "768P"]
WAN_RESOLUTIONS = ["1080p", "720p", "480p"]
H3_T2V_RATIOS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
WAN_T2V_RATIOS = ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"]

WAN_T2V_MODELS = ["alibaba/wan-3.0/text-to-video", "alibaba/wan-3.0-prime/text-to-video"]
WAN_I2V_MODELS = ["alibaba/wan-3.0/image-to-video", "alibaba/wan-3.0-prime/image-to-video"]


class _AtlasVideoBase:
    """Shared wiring for all four video nodes: outputs, the submit/poll/save run,
    and the two frame-encoding paths (data URL for h3, upload for wan)."""

    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "path")
    FUNCTION = "run_main"
    CATEGORY = CategoryList.api_atlas()
    OUTPUT_NODE = True   # it writes a file and previews the clip, like SaveImage

    # ---- shared widget tail ------------------------------------------------
    @staticmethod
    def _common_optional() -> dict:
        return {
            "your_api_key": ("STRING", {"multiline": False, "default": ""}),
            "timeout_minutes": ("INT", {"default": 30, "min": 1, "max": 240, "step": 1}),
            "filename_prefix": ("STRING", {"multiline": False, "default": "or_videos/video"}),
        }

    @staticmethod
    def _hidden() -> dict:
        # unique_id feeds the progress bar; ComfyUI injects it, never the user.
        return {"hidden": {"unique_id": "UNIQUE_ID"}}

    # ---- frame encoding ----------------------------------------------------
    @staticmethod
    def _frame_data_url(tensor, label: str) -> str:
        """h3 path: encode in memory, send as a base64 data URL (no upload hop)."""
        raw, mime = encode_frame(tensor, max_bytes=H3_MAX_FRAME_BYTES, label=label)
        return bytes_to_data_url(raw, mime)

    @staticmethod
    def _frame_public_url(tensor, api_key: str, label: str, name: str) -> str:
        """wan path: the API only accepts a PUBLIC URL, so upload to Atlas storage
        first and use the returned download_url."""
        check_frame_limits(tensor, label, min_edge=240, max_ratio=8.0)
        raw, mime = encode_frame(tensor, max_bytes=WAN_MAX_FRAME_BYTES, label=label)
        ext = "jpg" if mime == "image/jpeg" else "png"
        return upload_media(raw, mime, api_key, filename=f"{name}.{ext}")

    # ---- the async job -----------------------------------------------------
    def _run_job(self, payload: dict, api_key: str, *, timeout_minutes: int,
                 filename_prefix: str, unique_id=None):
        model = payload["model"]
        print(f"[atlas] submitting {model} ...")
        started = time.monotonic()

        prediction_id = submit_prediction(payload, api_key)
        print(f"[atlas] prediction {prediction_id} submitted — BILLED FROM HERE. "
              "Keep this id: a finished render can always be re-fetched.")

        progress = make_progress_bar(unique_id)
        budget = max(1, timeout_minutes) * 60

        def on_poll(status, elapsed):
            print(f"[atlas] {prediction_id}: {status or 'queued'} "
                  f"({elapsed:.0f}s elapsed)")
            if progress is not None:
                # Elapsed-time indicator against the timeout budget — NOT a
                # completion estimate (Atlas reports no percentage). Capped at 99
                # so the bar never claims "done" before the video exists.
                try:
                    progress.update_absolute(int(min(0.99, elapsed / budget) * 100))
                except Exception:
                    pass

        data = poll_prediction(prediction_id, api_key, timeout_minutes=timeout_minutes,
                               interval=POLL_INTERVAL, progress=on_poll)
        elapsed = time.monotonic() - started

        video_url = extract_video_url(data)
        report_cost(data, model, prediction_id, elapsed)

        video, path, saved_name, subfolder = download_and_save(video_url, filename_prefix)
        return {"result": (video, video_url, path),
                "ui": preview_video_ui(saved_name, subfolder)}


class AtlasH3MaxImageToVideo(_AtlasVideoBase):
    """minimax/h3-max/image-to-video — animate a first frame (optionally to a
    last frame). `ratio` is not exposed: Atlas documents that i2v always uses
    `adaptive` and IGNORES any other value, so a widget would be a lie."""

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            "end_image": ("IMAGE",),
            "resolution": (H3_RESOLUTIONS, {"default": "768P"}),
            "duration": ("INT", {"default": 8, "min": 5, "max": 15, "step": 1}),
            "prompt_expansion": ("BOOLEAN", {"default": False}),
        }
        optional.update(cls._common_optional())
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True,
                                      "default": "Describe the motion and camera move."}),
                "image": ("IMAGE",),
            },
            "optional": optional,
            **cls._hidden(),
        }

    def run_main(self, prompt, image, end_image=None, resolution="768P", duration=8,
                 prompt_expansion=False, your_api_key="", timeout_minutes=30,
                 filename_prefix="or_videos/video", unique_id=None):
        api_key = resolve_api_key(your_api_key)

        payload = {
            "model": "minimax/h3-max/image-to-video",
            "prompt": prompt,
            "image": self._frame_data_url(image, "image (first frame)"),
            "resolution": resolution,
            "duration": duration,
            "ratio": "adaptive",
            "prompt_expansion": prompt_expansion,
        }
        if end_image is not None:
            payload["end_image"] = self._frame_data_url(end_image, "end_image (last frame)")

        return self._run_job(payload, api_key, timeout_minutes=timeout_minutes,
                             filename_prefix=filename_prefix, unique_id=unique_id)


class AtlasH3MaxTextToVideo(_AtlasVideoBase):
    """minimax/h3-max/text-to-video — generate from a prompt alone."""

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            "resolution": (H3_RESOLUTIONS, {"default": "768P"}),
            "duration": ("INT", {"default": 8, "min": 5, "max": 15, "step": 1}),
            "ratio": (H3_T2V_RATIOS, {"default": "16:9"}),
            "prompt_expansion": ("BOOLEAN", {"default": False}),
        }
        optional.update(cls._common_optional())
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True,
                                      "default": "Describe the scene, subject and camera."}),
            },
            "optional": optional,
            **cls._hidden(),
        }

    def run_main(self, prompt, resolution="768P", duration=8, ratio="16:9",
                 prompt_expansion=False, your_api_key="", timeout_minutes=30,
                 filename_prefix="or_videos/video", unique_id=None):
        api_key = resolve_api_key(your_api_key)

        payload = {
            "model": "minimax/h3-max/text-to-video",
            "prompt": prompt,
            "resolution": resolution,
            "duration": duration,
            "ratio": ratio,
            "prompt_expansion": prompt_expansion,
        }
        return self._run_job(payload, api_key, timeout_minutes=timeout_minutes,
                             filename_prefix=filename_prefix, unique_id=unique_id)


class AtlasWanTextToVideo(_AtlasVideoBase):
    """alibaba/wan-3.0(/-prime)/text-to-video — prompt-only, native audio track.

    `seed` = -1 means "don't send a seed" (the API then picks one); any value
    >= 0 is sent.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            "model": (WAN_T2V_MODELS, {"default": WAN_T2V_MODELS[0]}),
            "resolution": (WAN_RESOLUTIONS, {"default": "1080p"}),
            "duration": ("INT", {"default": 5, "min": 2, "max": 30, "step": 1}),
            "ratio": (WAN_T2V_RATIOS, {"default": "adaptive"}),
            "audio": ("BOOLEAN", {"default": True}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
        }
        optional.update(cls._common_optional())
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True,
                                      "default": "Describe the scene, subject and camera."}),
            },
            "optional": optional,
            **cls._hidden(),
        }

    def run_main(self, prompt, model=None, resolution="1080p", duration=5,
                 ratio="adaptive", audio=True, seed=-1,
                 your_api_key="", timeout_minutes=30,
                 filename_prefix="or_videos/video", unique_id=None):
        api_key = resolve_api_key(your_api_key)

        payload = {
            "model": model or WAN_T2V_MODELS[0],
            "prompt": prompt,
            "resolution": resolution,
            "duration": duration,
            "ratio": ratio,
            "audio": audio,
        }
        if seed is not None and seed >= 0:
            payload["seed"] = seed

        return self._run_job(payload, api_key, timeout_minutes=timeout_minutes,
                             filename_prefix=filename_prefix, unique_id=unique_id)


class AtlasWanImageToVideo(_AtlasVideoBase):
    """alibaba/wan-3.0(/-prime)/image-to-video — strict first-frame mode with an
    optional last frame the model interpolates towards.

    No `ratio` widget: for i2v the framing comes from the input image. Frames are
    uploaded to Atlas storage first because wan accepts public URLs only.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            "last_image": ("IMAGE",),
            "model": (WAN_I2V_MODELS, {"default": WAN_I2V_MODELS[0]}),
            "resolution": (WAN_RESOLUTIONS, {"default": "1080p"}),
            "duration": ("INT", {"default": 5, "min": 2, "max": 30, "step": 1}),
            "audio": ("BOOLEAN", {"default": True}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
        }
        optional.update(cls._common_optional())
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True,
                                      "default": "Describe the motion and camera move."}),
                "image": ("IMAGE",),
            },
            "optional": optional,
            **cls._hidden(),
        }

    def run_main(self, prompt, image, last_image=None, model=None, resolution="1080p",
                 duration=5, audio=True, seed=-1,
                 your_api_key="", timeout_minutes=30,
                 filename_prefix="or_videos/video", unique_id=None):
        api_key = resolve_api_key(your_api_key)

        payload = {
            "model": model or WAN_I2V_MODELS[0],
            "prompt": prompt,
            "image": self._frame_public_url(image, api_key, "image (first frame)",
                                            "first_frame"),
            "resolution": resolution,
            "duration": duration,
            "audio": audio,
        }
        if last_image is not None:
            payload["last_image"] = self._frame_public_url(last_image, api_key,
                                                          "last_image (last frame)",
                                                          "last_frame")
        if seed is not None and seed >= 0:
            payload["seed"] = seed

        return self._run_job(payload, api_key, timeout_minutes=timeout_minutes,
                             filename_prefix=filename_prefix, unique_id=unique_id)
