import os
import json
import urllib.request
import urllib.error
from pathlib import Path
import base64
from folder_paths import get_output_directory

from .catogory_list import CategoryList

import io
import numpy as np
import torch
from PIL import Image


class ORImageGen:

    def tensor_to_data_url(self, tensor):  # (1,H,W,3) float 0-1 IMAGE tensor -> png data url
        img = Image.fromarray((tensor[0].numpy() * 255).astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


    def image_to_tensor(self, b64_string):
        buf = io.BytesIO(base64.b64decode(b64_string))
        img = Image.open(buf).convert("RGB")
        arr = np.array(img).astype("float32") / 255.0
        return torch.from_numpy(arr).unsqueeze(0)


    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "user_prompt": ("STRING", {"multiline": True, "default": "User prompt here."}),
                "model": ("STRING", {"multiline": False, "default": "qwen/qwen-image-3-pro"}),
                "aspect_ratio": (["1:1", "16:9", "9:16", "4:3", "3:4"], {"default": "16:9"}),
                "output_resolution": (["1K", "2K"], {"default": "1K"})
            },
            "optional": {
                "your_api_key": ("STRING", {"multiline": False, "default": ""}),
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",)
            }
        }


    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "path")
    FUNCTION = "run_main"
    CATEGORY = CategoryList.api_openrouter()


    def run_main(self, user_prompt, model, aspect_ratio, output_resolution, 
                 your_api_key, image_1=None, image_2=None, image_3=None, image_4=None):

        # check if api key presented
        your_api_key = your_api_key or os.environ.get("PERSONAL_OPENROUTER_TESTKEY")
        if not your_api_key:
            raise Exception("No OpenRouter API key: fill the widget or set PERSONAL_OPENROUTER_TESTKEY.")

        # build header
        headers = {
            "Authorization": f"Bearer {your_api_key}",
            "Content-Type": "application/json"
        }

        # build reference images
        reference_images = []
        for img in (image_1, image_2, image_3, image_4):
            if img is not None:
                reference_images.append({
                    "type": "image_url",
                    "image_url": {"url": self.tensor_to_data_url(img)}
                })

        # build body payload
        payload = {
            "model": model,
            "prompt": user_prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": output_resolution
        }

        if reference_images:
            payload["input_references"] = reference_images

        OPENROUTER_URL = "https://openrouter.ai/api/v1/images"

        # POST + Guard
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as err:
            raise Exception(f"Image request failed ({err.code}): {err.read().decode('utf-8')}")

        ## UNPACKS!!!
        data = json.loads(response.read().decode("utf-8"))

        first = data["data"][0]
        b64_string = first["b64_json"]
        ext = first.get("media_type", "image/png").split("/")[-1]  # .split("/")[-1] turns "image/png" into "png"

        # save
        #out_dir = Path("test_outputs")
        out_dir = Path(get_output_directory()) / "or_images"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"generated.{ext}"
        with open(out_path, "wb") as file:
            file.write(base64.b64decode(b64_string))

        # cost and return
        cost = data.get("usage", {}).get("cost", "n/a")
        print(f"Cost: {cost}")

        image_tensor = self.image_to_tensor(b64_string)
        return(image_tensor, str(out_path),)

        