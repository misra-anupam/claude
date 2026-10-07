from . import langgraph_v2_fallback, langgraph_v3_adapter


def get_adapter(version: str):
    if version == "v2":
        return langgraph_v2_fallback
    return langgraph_v3_adapter
