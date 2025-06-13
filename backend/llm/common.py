import copy
from db.models.common import ConversationHistory, ConversationType, MessageType
from llm.client_proxy import LlmMessage, LlmMessageType
from llm.tracker import LlmTracker
from llm.client_proxy_factory import get_default_client_proxy
from utils.http import ua
import requests

def flatten_schema_and_remove_defs(schema: dict) -> dict:
    """
    Remove $defs and replace all $ref with inline definitions
    """
    defs = schema.get("$defs", {})
    schema = copy.deepcopy(schema)
    if not defs:
        return schema

    def resolve_ref(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_key = obj["$ref"].split("/")[-1]
                return resolve_ref(defs[ref_key])
            else:
                return {k: resolve_ref(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_ref(i) for i in obj]
        else:
            return obj
    flat_schema = resolve_ref(schema)
    flat_schema.pop("$defs", None)
    return flat_schema

def from_db_conversation_history_to_llm_message(
    db_item: ConversationHistory,
) -> LlmMessage:
    if db_item.message_type == MessageType.HUMAN:
        llm_message_type = LlmMessageType.HUMAN
    elif db_item.message_type == MessageType.AI:
        llm_message_type = LlmMessageType.AI
    else:
        raise ValueError(f"Unsupported message type: {db_item.message_type}")
    return LlmMessage(
        text_content=db_item.content,
        type=llm_message_type,
    )

__raw_summary_prompt = "Summarize the following news into less than 100 words. The news is crawled from web. {content}"
__header = {"User-Agent": ua.random}

async def crawl_and_summarize_url(url: str, llm_tracker: LlmTracker) -> str:
    response = requests.get(url, headers=__header, timeout=10)
    response.raise_for_status()  # This will raise an exception for HTTP errors
    content = response.text
    # summarize the content
    return (await get_default_client_proxy().generate_content_async(
            prompt=__raw_summary_prompt.format_map(
                {"content": content}
            ),
            tracker=llm_tracker,
        ))[0].text_content
