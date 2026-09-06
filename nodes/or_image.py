import os
import requests
from pathlib import Path
import base64


class ORImageGen:

    def to_data_url(self, ref):  # Encode image to base64 data url
        if ref.startswith("http"):
            return ref

        raw = Path(ref).read_bytes()  # read the ref images raw data
        encoded = base64.b64encode(raw).decode()  # b64encode -> transform (byte) -> decode (byte -> string)
        ext_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime = ext_map.get(Path(ref).suffix.lower(), "image/png")
        return f"data:{mime};base64,{encoded}"


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
                "image_1": ("STRING", {"multiline": False, "default": ""}),  # Image as image URL or local path - single string
                "image_2": ("STRING", {"multiline": False, "default": ""}),
                "image_3": ("STRING", {"multiline": False, "default": ""}),
                "image_4": ("STRING", {"multiline": False, "default": ""})   
            }
        }


    RETURN_TYPES = ("STRING", )
    FUNCTION = "run_main"
    CATEGORY = "MyOpenRouter"


    def run_main(self, user_prompt, model, aspect_ratio, output_resolution, 
                 your_api_key, image_1, image_2, image_3, image_4):

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
            if img:
                reference_images.append({
                    "type": "image_url",
                    "image_url": {"url": self.to_data_url(img)}
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


        # POST + Guard
        response = requests.post(
            "https://openrouter.ai/api/v1/images",
            json=payload,
            headers=headers,
            timeout=180
        )

        if response.status_code != 200:
            raise Exception(f"Image request failed ({response.status_code}): {response.text}")
    

        ## UNPACKS!!!
        data = response.json()
        first = data["data"][0]
        b64_string = first["b64_json"]
        ext = first.get("media_type", "image/png").split("/")[-1]  # .split("/")[-1] turns "image/png" into "png"

        # save
        out_dir = Path("test_outputs")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"generated.{ext}"
        with open(out_path, "wb") as file:
            file.write(base64.b64decode(b64_string))

        # cost and return
        cost = data.get("usage", {}).get("cost", "n/a")
        print(f"Cost: {cost}")

        return(str(out_path),)

        