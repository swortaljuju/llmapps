import enum

class NewsSummaryPeriod(enum.Enum):
    # Daily summary
    daily = "daily"
    # Weekly summary
    weekly = "weekly"
    # Monthly summary. Not supported yet
    monthly = "monthly"