import os
import json
import urllib.request
import urllib.error
import base64
import io

import numpy as np
from PIL import Image

from .catogory_list import CategoryList

class ORTextEcho:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "hello bigbunnyball"}),
                "prefix": ("STRING", {"multiline": False, "default": "router"})
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run_text"
    CATEGORY = CategoryList.api_openrouter()


    def run_text(self, prefix, text):      # params match INPUT_TYPES keys
        return (f"{prefix}: {text}",)


class ORTextLLM:

    def tensor_to_data_url(self, tensor):  # (1,H,W,3) float 0-1 IMAGE tensor -> png data url
        img = Image.fromarray((tensor[0].numpy() * 255).astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "your_api_key": ("STRING", {"multiline": False, "default": ""}),
                "system_prompt": ("STRING", {"multiline": True, "default": ""}),
                "user_prompt": ("STRING", {"multiline": True, "default": "User prompt here."}),
                "model": ("STRING", {"multiline": False, "default": "qwen/qwen3.7-flash"}),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": 32000, "min": 8000, "max": 64000})
            },
            "optional": {
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
                "image_5": ("IMAGE",),
                "image_6": ("IMAGE",)
            }
        }

    RETURN_TYPES = ("STRING", )
    FUNCTION = "run_main"
    CATEGORY = CategoryList.api_openrouter()


    def run_main(self, your_api_key, system_prompt, user_prompt, model, temperature, max_tokens,
                 image_1=None, image_2=None, image_3=None, image_4=None, image_5=None, image_6=None):

        # get api key from env
        api_key = your_api_key or os.environ.get("PERSONAL_OPENROUTER_TESTKEY")
        if not api_key:
            raise Exception("Please set an OpenRouter api key in system environment variables..")

        # build header dict
        header = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # build user message: plain text, or multipart (text first, then images) per docs
        images = [t for t in (image_1, image_2, image_3, image_4, image_5, image_6) if t is not None]
        if images:
            user_content = [{"type": "text", "text": user_prompt}]
            for t in images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": self.tensor_to_data_url(t)}
                })
        else:
            user_content = user_prompt

        # build body payload dict
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # # POST it
        # OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
        # response = requests.post(OPENROUTER_URL, json=payload, headers=header, timeout=60)
        # #print(response.text)

        # # check status code
        # if response.status_code != 200:
        #     raise Exception(f"Request Unsuccessful: {response.text}")

        # # parse response JSON
        # data = response.json()

        # Post it
        OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=header,
            method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            raise Exception(f"Request Unsuccessful ({e.code}): {e.read().decode('utf-8')}")

        # Parse response json
        data = json.loads(response.read().decode("utf-8"))

        print(f"Cost: {data['usage']['cost']}")

        # response message - content and reasoning
        response_message = data["choices"][0]["message"]

        content = response_message.get("content")
        reasoning = response_message.get("reasoning")

        # fallback: reasoning model ran out of budget before writing the answer
        if not content:
            content = "[reasoning only] " + (reasoning or "")

        # label a cut-off answer instead of shipping it silently
        if data["choices"][0]["finish_reason"] == "length":
            content = content + " [truncated: increase max_tokens]"

        return (content,)