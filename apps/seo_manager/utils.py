from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Tuple

def get_monthly_date_ranges(months_back: int = 12) -> List[Tuple[date, date]]:
    """
    Generate a list of (start_date, end_date) tuples for each month
    going back X months from today.
    """
    today = date.today()
    ranges = []
    
    for i in range(months_back):
        # Get first day of the month
        end_date = today - relativedelta(months=i)
        start_date = end_date.replace(day=1)
        
        # For current month, use today as end_date
        if i == 0:
            ranges.append((start_date, today))
        else:
            # Get last day of the month
            end_date = (start_date + relativedelta(months=1) - timedelta(days=1))
            ranges.append((start_date, end_date))
    
    return ranges
