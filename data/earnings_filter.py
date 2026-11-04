import yfinance as yf
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

class EarningsSafetyFilter:
    """
    Checks if a stock has an upcoming earnings announcement within N days.
    Prevents holding through catastrophic post-earnings gap downs.
    """
    def __init__(self, blackout_days: int = 5):
        self.blackout_days = blackout_days

    def check_earnings_risk(self, ticker: str) -> Dict[str, any]:
        """
        Returns earnings risk status:
        {
            'has_upcoming_earnings': bool,
            'days_until_earnings': int or None,
            'earnings_date_str': str or None,
            'is_safe_to_buy': bool
        }
        """
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            
            earnings_date = None
            if cal is not None:
                if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
                    earnings_date = cal['Earnings Date'][0]
                elif hasattr(cal, 'get') and cal.get('Earnings Date'):
                    earnings_date = cal.get('Earnings Date')[0]
                elif isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.index:
                    earnings_date = cal.loc['Earnings Date'].iloc[0]

            if earnings_date:
                now = datetime.now()
                # If earnings_date is timestamp or date
                if hasattr(earnings_date, 'to_pydatetime'):
                    dt = earnings_date.to_pydatetime()
                elif hasattr(earnings_date, 'date'):
                    dt = datetime.combine(earnings_date.date(), datetime.min.time())
                else:
                    dt = pd.to_datetime(earnings_date).to_pydatetime()

                # Make naive for comparison
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)

                days_diff = (dt - now).days
                if 0 <= days_diff <= self.blackout_days:
                    return {
                        "has_upcoming_earnings": True,
                        "days_until_earnings": days_diff,
                        "earnings_date_str": dt.strftime("%Y-%m-%d"),
                        "is_safe_to_buy": False
                    }
                else:
                    return {
                        "has_upcoming_earnings": False,
                        "days_until_earnings": days_diff if days_diff >= 0 else None,
                        "earnings_date_str": dt.strftime("%Y-%m-%d") if days_diff >= 0 else None,
                        "is_safe_to_buy": True
                    }

            return {
                "has_upcoming_earnings": False,
                "days_until_earnings": None,
                "earnings_date_str": None,
                "is_safe_to_buy": True
            }
        except Exception:
            # If calendar cannot be read, default to safe
            return {
                "has_upcoming_earnings": False,
                "days_until_earnings": None,
                "earnings_date_str": None,
                "is_safe_to_buy": True
            }
