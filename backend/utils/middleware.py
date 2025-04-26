from fastapi import  Request
from starlette.middleware.base import BaseHTTPMiddleware
from db import db
from db.models import (
    ApiLatencyLog,
)
import time


class ApiLatencyLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timer for performance logging
        start_time = time.time()

        # Extract the path for logging
        path = request.url.path
        # Check for authentication session
        request.state.api_latency_log = ApiLatencyLog(
            api_path=path,
        )
        # Continue with the request
        response = await call_next(request)
        # Log response time
        process_time = time.time() - start_time
        request.state.api_latency_log.total_elapsed_time_ms = int(
            process_time * 1000
        )
        sql_client = db.get_sql_db()
        sql_client.add(request.state.api_latency_log)
        sql_client.commit()
        return response