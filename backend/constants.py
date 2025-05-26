ONE_WEEK_IN_SECONDS = 7 * 24 * 60 * 60  # 7 days * 24 hours * 60 minutes * 60 seconds
# Header to fake the user agent to avoid bot detection
HTTP_HEADER_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
MAX_USER_COUNT_PER_USER_TIER = {"unlimited": 10, "full_experimentation": 20, "basic": 1}
MAX_RSS_SUBSCRIPTION = 100
SQL_BATCH_SIZE = 1000
MAX_INPUT_TOKENS_PER_USER_PER_MONTH = 100000000  # 100 million tokens
MAX_OUTPUT_TOKENS_PER_USER_PER_MONTH = 100000000  # 100 million tokens