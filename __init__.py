from .nodes.or_text import ORTextEcho, ORTextLLM
from .nodes.or_image import ORImageGen
from .nodes.atlas_video import (
    AtlasH3MaxImageToVideo,
    AtlasH3MaxTextToVideo,
    AtlasWanTextToVideo,
    AtlasWanImageToVideo,
)


NODE_CLASS_MAPPINGS = {
    "ORTextEcho": ORTextEcho,
    "ORTextLLM": ORTextLLM,
    "ORImageGen": ORImageGen,
    "AtlasH3MaxImageToVideo": AtlasH3MaxImageToVideo,
    "AtlasH3MaxTextToVideo": AtlasH3MaxTextToVideo,
    "AtlasWanTextToVideo": AtlasWanTextToVideo,
    "AtlasWanImageToVideo": AtlasWanImageToVideo,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "ORTextEcho": "OpenRouter Text Echo",
    "ORTextLLM": "OpenRouter Text LLM",
    "ORImageGen": "OpenRouter Image Generation",
    "AtlasH3MaxImageToVideo": "Atlas Cloud MiniMax H3 Max Image to Video",
    "AtlasH3MaxTextToVideo": "Atlas Cloud MiniMax H3 Max Text to Video",
    "AtlasWanTextToVideo": "Atlas Cloud Wan 3.0 Text to Video",
    "AtlasWanImageToVideo": "Atlas Cloud Wan 3.0 Image to Video",
}