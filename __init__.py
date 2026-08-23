from .nodes.or_text import ORTextEcho, ORTextLLM

NODE_CLASS_MAPPINGS = {
    "ORTextEcho": ORTextEcho,
    "ORTextLLM": ORTextLLM
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ORTextEcho": "OR Text Echo",
    "ORTextLLM": "OR Text LLM"
}