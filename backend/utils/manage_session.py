from fastapi import Cookie, Depends, Response, HTTPException, status
from db import db
from typing import Annotated
from pydantic import BaseModel
import uuid
from constants import ONE_WEEK_IN_SECONDS
import os

UNLIMITED_USER_EMAILS = os.getenv("UNLIMITED_USER_EMAILS", "").split(",")
CALLS_PER_WEEK = os.getenv("CALLS_PER_WEEK", 500)
LIMIT_USAGE_REDIS_KEY = "limit_usage"


class SessionUser(BaseModel):
    user_id: int
    email: str


async def get_user_in_session(
    session_id: Annotated[str | None, Cookie()], redis: db.RedisClient
) -> SessionUser | None:
    user = await redis.get(f"session:{session_id}")
    if user is None:
        return None
    return SessionUser.model_validate_json(user)


async def cache_user_in_session(
    user_id: int, email: str, redis_client: db.RedisClient, response: Response
) -> None:
    # Generate session ID
    session_id = str(uuid.uuid4())
    # Store session in Redis with 1 week expiry
    await redis_client.set(
        f"session:{session_id}",
        SessionUser(id=user_id, email=email).model_dump_json(),
        ex=ONE_WEEK_IN_SECONDS,
    )

    # Set cookie with session ID
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=ONE_WEEK_IN_SECONDS,
        samesite="lax",  # Provides CSRF protection
    )


GetUserInSession = Annotated[str | None, Depends(get_user_in_session)]


async def limit_usage(user: GetUserInSession, redis: db.RedisClient) -> None:
    # Check if user is not found in session
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user in session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Check if user has unlimited access
    if user.email in UNLIMITED_USER_EMAILS:
        return
    redis.set(
        name=LIMIT_USAGE_REDIS_KEY,
        value=CALLS_PER_WEEK,
        ex=ONE_WEEK_IN_SECONDS,
        nx=True,
    )
    decr_result = redis.decr(LIMIT_USAGE_REDIS_KEY)
    if decr_result < 0:
        pttl_result = redis.pttl(LIMIT_USAGE_REDIS_KEY)
        if pttl_result == -1:
            redis.set(
                name=LIMIT_USAGE_REDIS_KEY,
                value=(CALLS_PER_WEEK - 1),
                ex=ONE_WEEK_IN_SECONDS,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"WWW-Authenticate": "Bearer"},
            )
