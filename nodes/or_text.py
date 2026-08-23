import os
import requests


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
    CATEGORY = "MyOpenRouter"


    def run_text(self, prefix, text):      # params match INPUT_TYPES keys
        return (f"{prefix}: {text}",)


class ORTextLLM:

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
            }
        }

    RETURN_TYPES = ("STRING", )
    FUNCTION = "run_main"
    CATEGORY = "MyOpenRouter"


    def run_main(self, your_api_key, system_prompt, user_prompt, model, temperature, max_tokens):

        # get api key from env
        api_key = your_api_key or os.environ.get("PERSONAL_OPENROUTER_TESTKEY")
        if not api_key:
            raise Exception("Please set an OpenRouter api key in system environment variables..")

        # build header dict
        header = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

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
                    "content": user_prompt
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # POST it
        OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
        response = requests.post(OPENROUTER_URL, json=payload, headers=header, timeout=60)
        #print(response.text)

        # check status code
        if response.status_code != 200:
            raise Exception(f"Request Unsuccessful: {response.text}")

        # parse response JSON
        data = response.json()
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