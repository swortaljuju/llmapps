from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env
load_dotenv(find_dotenv(filename='.env.local'))  # Load local environment variables if available

from fastapi import FastAPI
from routers import user_management, news_summary
from utils.middleware import ApiLatencyLogMiddleware
### Create FastAPI instance with custom docs and openapi url
app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

app.include_router(user_management.router)
app.include_router(news_summary.router)
app.add_middleware(ApiLatencyLogMiddleware)

@app.get("/api/py/helloFastApi")
def hello_fast_api():
    return {"message": "Hello from FastAPI"}
