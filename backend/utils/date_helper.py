from datetime import date, timedelta
from db.models import  NewsSummaryPeriod

def is_valid_period_start_date(start_date: date, period_type: NewsSummaryPeriod) -> bool:
    """
    Validate that the start date is valid for the given period type.
    """
    if period_type == NewsSummaryPeriod.daily:
        return True
    elif period_type == NewsSummaryPeriod.weekly:
        # Check if the start date is a Monday
        return start_date.weekday() == 0
    elif period_type == NewsSummaryPeriod.monthly:
        # Check if the start date is the first day of the month
        return start_date.day == 1
    else:
        raise ValueError(f"Invalid period type: {period_type}")

def determine_period_inclusive_end_date(period_type: NewsSummaryPeriod, start_date: date) -> date:
    """
    Determine the start date based on the period type.
    """
    if period_type == NewsSummaryPeriod.daily:
        return start_date
    elif period_type == NewsSummaryPeriod.weekly:
        return start_date + timedelta(days=6)
    elif period_type == NewsSummaryPeriod.monthly:
        # For monthly periods, get the last day of the month
        if start_date.month == 12:
            # If December, the end date is December 31st
            return date(start_date.year, 12, 31)
        else:
            # Otherwise, it's the day before the 1st of next month
            next_month = date(start_date.year, start_date.month + 1, 1)
            return next_month - timedelta(days=1)
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
