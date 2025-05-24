from datetime import date, timedelta
from db.models import  NewsSummaryPeriod

def determine_start_date(period_type: NewsSummaryPeriod, end_date: date) -> date:
    """
    Determine the start date based on the period type.
    """
    if period_type == NewsSummaryPeriod.daily:
        return end_date
    elif period_type == NewsSummaryPeriod.weekly:
        return end_date - timedelta(days=end_date.weekday())
    else:
        raise ValueError(f"Invalid period type: {period_type}")

def get_period_length(period_type: NewsSummaryPeriod) -> timedelta:
    """
    Get the length of the period in days.
    """
    if period_type == NewsSummaryPeriod.daily:
        return timedelta(days=1)
    elif period_type == NewsSummaryPeriod.weekly:
        return timedelta(weeks=1)
    else:
        raise ValueError(f"Invalid period type: {period_type}")
