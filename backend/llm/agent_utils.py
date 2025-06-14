from db.models.common import ConversationHistory, MessageType
from llm.client_proxy import LlmMessage, LlmMessageType
from llm.tracker import LlmTracker
from llm.client_proxy_factory import get_default_client_proxy
from utils.http import ua
import requests

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
