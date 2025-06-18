from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env
load_dotenv(find_dotenv(filename='.env.local'))  # Load local environment variables if available

from fastapi import FastAPI, Request, HTTPException
from routers import user_management, news_summary
from utils.middleware import ApiLatencyLogMiddleware, DbLifeCycleMiddleware
from utils.exceptions import ApiException, ApiErrorType, UserErrorCode
from utils.logger import logger, setup_logger

setup_logger("fastapi")
### Create FastAPI instance with custom docs and openapi url
app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

app.include_router(user_management.router)
app.include_router(news_summary.router)
app.add_middleware(ApiLatencyLogMiddleware)
app.add_middleware(DbLifeCycleMiddleware)

@app.exception_handler(ApiException)
async def generic_exception_handler(request: Request, e: ApiException):
    logger.error(f"Exception occurred: {e}")
    if e.type == ApiErrorType.CLIENT_ERROR:       
        raise HTTPException(
            status_code=400,
            detail=e.message,
        )  
    else:
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )
            
@app.get("/api/py/helloFastApi")
def hello_fast_api():
    return {"message": "Hello from FastAPI"}
