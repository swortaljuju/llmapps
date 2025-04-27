from db.models.common import ConversationHistory, ConversationType, LangChainMessageType
from pydantic import BaseModel
from langchain_core.messages import  HumanMessage, AIMessage, ToolMessage, SystemMessage
from collections import deque
import json
import uuid

class ApiConversationHistoryItem(BaseModel):
    user_id: int
    thread_id: str
    message_id: str
    parent_message_id: str | None = None
    human_message: HumanMessage | None = None
    ai_message: AIMessage | None = None
    tool_message: ToolMessage | None = None
    system_message: SystemMessage | None = None
    
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
            json_content = json.loads(current_item.content)
            if current_item.lang_chain_message_type == LangChainMessageType.HUMAN:
                api_conversation_history_item.human_message = HumanMessage(**json_content)
            elif current_item.lang_chain_message_type == LangChainMessageType.AI:
                api_conversation_history_item.ai_message = AIMessage(**json_content)
            elif current_item.lang_chain_message_type == LangChainMessageType.TOOL:
                api_conversation_history_item.tool_message = ToolMessage(**json_content)
            elif current_item.lang_chain_message_type == LangChainMessageType.SYSTEM:
                api_conversation_history_item.system_message = SystemMessage(**json_content)
            else:
                continue
            api_sub_conversation_history.appendleft(api_conversation_history_item)
            current_message_id = current_item.parent_message_id
        api_conversation_history.extend(api_sub_conversation_history)    
    
    return api_conversation_history

def convert_api_conversation_history_item_to_db_row(
    item: ApiConversationHistoryItem,
    user_id: int,
    conversation_type: ConversationType = ConversationType.news_preference_survey
) -> ConversationHistory:
    """
    Converts an ApiConversationHistoryItem to a ConversationHistory item for database storage.
    """
    content = {}
    if item.human_message:
        content = item.human_message.model_dump()
        lang_chain_message_type = LangChainMessageType.HUMAN
    elif item.ai_message:
        content = item.ai_message.model_dump()
        lang_chain_message_type = LangChainMessageType.AI
    elif item.tool_message:
        content = item.tool_message.model_dump()
        lang_chain_message_type = LangChainMessageType.TOOL
    elif item.system_message:
        content = item.system_message.model_dump()
        lang_chain_message_type = LangChainMessageType.SYSTEM
    
    return ConversationHistory(
        user_id=user_id,
        thread_id=item.thread_id,
        message_id=item.message_id,
        parent_message_id=item.parent_message_id,
        content=json.dumps(content),
        lang_chain_message_type=lang_chain_message_type,
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