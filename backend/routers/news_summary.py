from fastapi import APIRouter, HTTPException, status
from typing import Optional
from pydantic import BaseModel
from db import db
from db.models import User, NewsSummary, NewsSummaryList
from utils.manage_session import GetUserInSession
from datetime import date
import os

DOMAIN = os.getenv("DOMAIN", "localhost:3000")

router = APIRouter(prefix="/api/py/news_summary", tags=["users"])

class NewsSummaryPeriod(BaseModel):
    start_date_timestamp: int # Timestamp in seconds
    end_date_timestamp: int # Timestamp in seconds
    id: int
class NewsSummaryInitializeResponse(BaseModel):
    mode: str
    latest_summary: Optional[NewsSummaryList] = None
    news_summary_periods: list[NewsSummaryPeriod]

@router.get("/initialize", response_model=NewsSummaryInitializeResponse)
async def initialize(user: GetUserInSession, db: db.SqlClient):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Query user data
    user_data = db.query(User).filter(User.id == user.user_id).first()
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check news preference
    if not user_data.news_preference:
        return NewsSummaryInitializeResponse(mode="collect_news_preference")
    
    # Check RSS feeds subscription
    if not user_data.subscribed_rss_feeds_id:
        return NewsSummaryInitializeResponse(mode="collect_rss_feeds")
    
    # Query latest news summary
    all_summary = (
        db.query(NewsSummary)
        .filter(
            NewsSummary.user_id == user.user_id
        )
        .order_by(NewsSummary.end_date.desc())
        .all()
    )
    
    return NewsSummaryInitializeResponse(
        mode="show_summary",
        latest_summary = len(all_summary) > 0 and all_summary[0].content or None,
        news_summary_periods=[
            NewsSummaryPeriod(
                start_date_timestamp=int(summary.start_date.timestamp()),
                end_date_timestamp=int(summary.end_date.timestamp()),
                id=summary.id
            ) for summary in all_summary
        ]
    )
