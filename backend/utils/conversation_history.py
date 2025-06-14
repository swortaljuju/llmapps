from db.models.common import ConversationHistory, ConversationType, MessageType
from pydantic import BaseModel
from collections import deque
import uuid
from llm.client_proxy import LlmMessage, LlmMessageType
from backend.llm.agent_utils import from_db_conversation_history_to_llm_message
class ApiConversationHistoryItem(BaseModel):
    user_id: int
    thread_id: str
    message_id: str
    parent_message_id: str | None = None
    llm_message: LlmMessage | None = None
    
def convert_to_api_conversation_history(db_conversation_history: list[ConversationHistory]) -> list[ApiConversationHistoryItem]:
    '''
        Converts a list of ConversationHistory items from the database to a list of ApiConversationHistoryItem for 
        a particular thread. Ordered by hierarchical info in parent_message_id.
    '''
    if not db_conversation_history:
        return []
    
    message_id_map = {item.message_id: item for item in db_conversation_history}
    api_conversation_history = []
    for item in db_conversation_history:
        if item.message_id not in message_id_map:
            continue
        current_message_id = item.message_id
        api_sub_conversation_history = deque()
        while current_message_id is not None and (not api_conversation_history or len(api_conversation_history) > 0 and api_conversation_history[-1].message_id != current_message_id):
            current_item = message_id_map[current_message_id]
            del message_id_map[current_message_id]
            api_conversation_history_item = ApiConversationHistoryItem(
                user_id=current_item.user_id,
                thread_id=current_item.thread_id,
                message_id=current_item.message_id,
                parent_message_id=current_item.parent_message_id
            )
            llm_message = from_db_conversation_history_to_llm_message(current_item)
            
            api_conversation_history_item.llm_message = llm_message
            api_sub_conversation_history.appendleft(api_conversation_history_item)
            current_message_id = current_item.parent_message_id
        api_conversation_history.extend(api_sub_conversation_history)    
    
    return api_conversation_history

def convert_api_conversation_history_item_to_db_row(
    item: ApiConversationHistoryItem,
    user_id: int,
    conversation_type: ConversationType = ConversationType.news_preference_survey
) -> ConversationHistory| None:
    """
    Converts an ApiConversationHistoryItem to a ConversationHistory item for database storage.
    """
    content = item.llm_message.text_content
    llm_message_type = item.llm_message.type
    message_type = MessageType.UNKNOWN
    content = item.llm_message.text_content or ""
    if llm_message_type == LlmMessageType.HUMAN:
        message_type = MessageType.HUMAN
    elif llm_message_type == LlmMessageType.AI:
        message_type = MessageType.AI
    else:
        return None
    
    return ConversationHistory(
        user_id=user_id,
        thread_id=item.thread_id,
        message_id=item.message_id,
        parent_message_id=item.parent_message_id,
        content=content,
        message_type=message_type,
        conversation_type=conversation_type
    )

def create_thread_id() -> str:
    """
    Creates a new thread ID for conversation history.
    """
    return f"thread_id:{uuid.uuid4()}"

def create_message_id() -> str:
    """
    Creates a new message ID for conversation history.
    """
    return f"message_id:{uuid.uuid4()}"