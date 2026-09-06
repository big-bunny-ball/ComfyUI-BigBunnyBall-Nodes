from .nodes.or_text import ORTextEcho, ORTextLLM
from .nodes.or_image import ORImageGen


NODE_CLASS_MAPPINGS = {
    "ORTextEcho": ORTextEcho,
    "ORTextLLM": ORTextLLM,
    "ORImageGen": ORImageGen
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "ORTextEcho": "OpenRouter Text Echo",
    "ORTextLLM": "OpenRouter Text LLM",
    "ORImageGen": "OpenRouter Image Generation"
}