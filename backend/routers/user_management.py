from fastapi import APIRouter, HTTPException, status, Response
from utils.manage_session import GetUserInSession, cache_user_in_session
from db import db
import uuid
from db.models import User, UserStatus, UserTier
from passlib.context import CryptContext
from pydantic import BaseModel, constr, Field
from utils.mailer import send_email
import os
from constants import ONE_WEEK_IN_SECONDS, MAX_USER_COUNT_PER_USER_TIER
from fastapi.responses import HTMLResponse
from utils.logger import logger
import redis.asyncio as redis
import json

DOMAIN = os.getenv("DOMAIN", "localhost:3000")
INVITATION_CODE_USER_TIER_MAP = json.loads(os.getenv("INVITATION_CODE_USER_TIER_MAP",""))

router = APIRouter(prefix="/api/py/users", tags=["users"])


class SignInUser(BaseModel):
    name: constr(min_length=3, max_length=20)
    password: constr(min_length=4, max_length=20)


class SignUpUser(SignInUser):
    email: str = Field(pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    invitation_code: str

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


@router.get("/has_valid_session")
async def has_valid_session(user: GetUserInSession):
    try:
        # Check if specific session ID exists in Redis
        return {"valid": user is not None}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.post("/signin")
async def signin(
    signin_user: SignInUser,
    db: db.SqlClient,
    response: Response,
    redis_client: db.RedisClient,
):
    # Query user from postgres
    user = db.query(User).filter(User.name == signin_user.name).first()

    # Check if user exists
    if not user:
        logger.error(f"User not found: {signin_user.name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(signin_user.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.active:
        logger.error(f"User not verified: {signin_user.name}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email not verified",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await cache_user_in_session(user.id, user.email, redis_client, response)

    return {
        "status": "success",
    }

async def send_verification_email(receiver_email: str, redis_client: redis.Redis, user_id: int):
    """
    This function sends a verification email to the user after signing up.
    """
    # Create verification token
    verification_token = str(uuid.uuid4())

    # Create verification link
    verification_link = f"http://{DOMAIN}/api/py/users/verify/{verification_token}"

    # Send email using the send_email function
    send_email(
        receiver_email,
        subject="Verify your llm app account",
        content=f"Click the link to verify your account: {verification_link}",
    )
    
    await redis_client.set(
        f"verification:{verification_token}", str(user_id), ex=ONE_WEEK_IN_SECONDS
    )

@router.post("/signup")
async def signup(
    signup_user: SignUpUser, db: db.SqlClient, redis_client: db.RedisClient
):
    # Check if user name or email already exists
    existing_user = (
        db.query(User)
        .filter(
            (User.name == signup_user.name) | (User.email == signup_user.email)
        )
        .first()
    )

    if existing_user:
        if existing_user.name == signup_user.name and existing_user.email == signup_user.email:
            # Resend verification email if the same email and name are used again
            await send_verification_email(signup_user.email, redis_client, existing_user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User name and email already exists. A verification email has been resent.",
            )
        elif existing_user.name == signup_user.name:    
            logger.error(f"User name already exists: {signup_user.name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User name already exists",
            )
        else:
            logger.error(f"Email already registered: {signup_user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
    user_tier = INVITATION_CODE_USER_TIER_MAP.get(signup_user.invitation_code)
    if user_tier is None:
        logger.error(f"Invalid invitation code: {signup_user.invitation_code}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation code",
        )
    
    # Check if we've reached the limit for this user tier
    existing_users_count = db.query(User).filter(User.user_tier == UserTier(user_tier)).count()
    max_users_allowed = MAX_USER_COUNT_PER_USER_TIER.get(user_tier, 0)

    if existing_users_count >= max_users_allowed:
        logger.error(f"User tier {user_tier} has reached its limit")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User tier {user_tier} has reached its limit",
        )

    # Set the user tier in the new user
    new_user_tier = UserTier(user_tier)
    # Create new user
    new_user = User(
        name=signup_user.name,
        email=signup_user.email,
        hashed_password=get_password_hash(signup_user.password),
        status=UserStatus.pending,
        user_tier=new_user_tier,
    )

    # Add to database
    db.add(new_user)
    db.flush()
    await send_verification_email(signup_user.email, redis_client, new_user.id)
    

    return {
        "status": "success",
        "message": "Please check your email to verify your account",
    }


@router.get("/verify/{verification_token}")
async def verify(
    verification_token: str, db: db.SqlClient, redis_client: db.RedisClient
):
    user_id = int(await redis_client.get(f"verification:{verification_token}"))

    if not user_id:
        logger.error(f"Verification token expired or invalid: {verification_token}")
        return HTMLResponse(
            content="""
                <html>
                    <head>
                        <title>Verification Error</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
                            .error { color: #dc2626; }
                        </style>
                    </head>
                    <body>
                        <h2 class="error">Verification Failed</h2>
                        <p>The verification link has expired or is invalid.</p>
                    </body>
                </html>
            """
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.error(f"User not found for verification token: {verification_token}")
        return HTMLResponse(
            content="""
                <html>
                    <head>
                        <title>Verification Error</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
                            .error { color: #dc2626; }
                        </style>
                    </head>
                    <body>
                        <h2 class="error">Verification Failed</h2>
                        <p>User account not found.</p>
                    </body>
                </html>
            """
        )

    user.status = UserStatus.active

    await redis_client.delete(f"verification:{verification_token}")

    return HTMLResponse(
        content="""
            <html>
                <head>
                    <title>Verification Success</title>
                    <style>
                        body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
                        .success { color: #059669; }
                    </style>
                    <script>
                        setTimeout(function() {
                            window.location.href = '/';
                        }, 5000);
                    </script>
                </head>
                <body>
                    <h2 class="success">Account Verified Successfully!</h2>
                    <p>Your account has been verified. You will be redirected to the login page in 5 seconds.</p>
                    <p>If you are not redirected, <a href="/">click here</a>.</p>
                </body>
            </html>
        """
    )
