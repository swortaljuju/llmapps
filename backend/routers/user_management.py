from fastapi import APIRouter, HTTPException, status, Response
from utils.manage_session import GetUserInSession, set_user_in_session
from db import db
import uuid
from db.models import User, UserStatus
from passlib.context import CryptContext
from pydantic import BaseModel, constr
from utils.mailer import send_email
import os
from constants import ONE_WEEK_IN_SECONDS
from fastapi.responses import HTMLResponse

DOMAIN = os.getenv("DOMAIN", "http://localhost:8000")

router = APIRouter(prefix="/users", tags=["users"])


class SignInUser(BaseModel):
    username: constr(min_length=3, max_length=20)
    password: constr(min_length=4, max_length=20)


class SignUpUser(SignInUser):
    email: constr(regex=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


@router.get("/has_valid_session/{session_id}")
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
    user = db.query(User).filter(User.username == signin_user.username).first()

    # Check if user exists
    if not user:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email not verified",
            headers={"WWW-Authenticate": "Bearer"},
        )

    set_user_in_session(user.id, user.email, redis_client, response)

    return {
        "status": "success",
    }


@router.post("/signup")
async def signup(
    signup_user: SignUpUser, db: db.SqlClient, redis_client: db.RedisClient
):
    # Check if username or email already exists
    existing_user = (
        db.query(User)
        .filter(
            (User.username == signup_user.username) | (User.email == signup_user.email)
        )
        .first()
    )

    if existing_user:
        if existing_user.username == signup_user.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Create verification token
    verification_token = str(uuid.uuid4())

    # Create new user
    new_user = User(
        username=signup_user.username,
        email=signup_user.email,
        hashed_password=get_password_hash(signup_user.password),
        status=UserStatus.pending,
    )

    # Add to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Send verification email
    verification_link = f"http://{DOMAIN}/users/verify/{verification_token}"
    send_email(
        receiver_email=signup_user.email,
        subject="Verify your llm app account",
        content=f"Click the link to verify your account: {verification_link}",
    )

    redis_client.set(
        f"verification:{verification_token}", str(new_user.id), ex=ONE_WEEK_IN_SECONDS
    )

    return {
        "status": "success",
        "message": "Please check your email to verify your account",
    }


@router.post("/verify/{verification_token}")
async def verify(
    verification_token: str, db: db.SqlClient, redis_client: db.RedisClient
):
    user_id = int(await redis_client.get(f"verification:{verification_token}"))

    if not user_id:
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
    db.commit()

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
