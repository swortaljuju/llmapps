from db.models.common import ConversationHistory, MessageType
from llm.client_proxy import LlmMessage, LlmMessageType
from llm.tracker import LlmTracker
from llm.client_proxy_factory import get_default_client_proxy
from utils.http import ua
import requests
from utils.logger import logger

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

__raw_summary_prompt = "Summarize the following news into less than 100 words. Don't mention word number restriction. The news is crawled from web. {content}"
__header = {"User-Agent": ua.random}
__web_search_prompt = """
        Summarize the content in the urls into less than 100 words. Don't mention word number restriction.
        {url}
    """

async def crawl_and_summarize_url(url_list: list[str], llm_tracker: LlmTracker) -> str:
    content_list = []
    for url in url_list:
        try:
            response = requests.get(url, headers=__header, timeout=10)
            response.raise_for_status()  # This will raise an exception for HTTP errors
            content_list.append(response.text)
        except Exception as e:
            logger.error(f"Failed to crawl {url}: {str(e)}")
            continue
    # summarize the content
    if content_list:
        return (await get_default_client_proxy().generate_content_async(
            prompt=__raw_summary_prompt.format_map(
                {"content": "\n\n".join(content_list)}
            ),
            tracker=llm_tracker,
        ))[0].text_content
    
    return (await get_default_client_proxy().generate_content_async(
            prompt=__web_search_prompt.format_map(
                {"url": url_list}
            ),
            tracker=llm_tracker,
        ))[0].text_content
