from enum import Enum

class ApiErrorType(Enum):
    SERVER_ERROR = "SERVER_ERROR"
    CLIENT_ERROR = "CLIENT_ERROR"

class UserErrorCode(Enum):
    TOKEN_LIMIT_EXCEEDED = "TOKEN_LIMIT_EXCEEDED"
    NO_RSS_FEED_SUBSCRIBED = "NO_RSS_FEED_SUBSCRIBED"

class ApiException(Exception):
    def __init__(self, type: ApiErrorType, user_error_code: UserErrorCode = None, message: str = None) -> None:
        super().__init__(message)
        self.type = type
        self.user_error_code = user_error_code
        if user_error_code == UserErrorCode.TOKEN_LIMIT_EXCEEDED:
            self.message = "User has exceeded monthly token limit."
        elif user_error_code == UserErrorCode.NO_RSS_FEED_SUBSCRIBED:
            self.message = "User has not subscribed to any RSS feed."    
        else:
            self.message = message