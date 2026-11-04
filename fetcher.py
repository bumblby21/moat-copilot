import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

class MarketDataFetcher:
    """
    Downloads historical US stock & macro data and calculates technical/volatility indicators.
    """
    def __init__(self, tickers: List[str] = None):
        self.tickers = tickers or []

    def fetch_macro_state(self) -> Dict[str, float]:
        """
        Fetches current macro risk regime: S&P500 200SMA distance, VIX level, 10Y Yield.
        """
        try:
            vix = yf.Ticker("^VIX").history(period="5d")
            sp500 = yf.Ticker("^GSPC").history(period="1y")
            tnx = yf.Ticker("^TNX").history(period="5d")

            current_vix = float(vix['Close'].iloc[-1]) if not vix.empty else 18.0
            vix_change = float(vix['Close'].pct_change().iloc[-1] * 100) if len(vix) > 1 else 0.0

            sp_close = sp500['Close']
            sp_200sma = sp_close.rolling(200).mean().iloc[-1]
            sp_current = sp_close.iloc[-1]
            sp_trend_bullish = bool(sp_current > sp_200sma)

            current_tnx = float(tnx['Close'].iloc[-1]) if not tnx.empty else 4.0

            # Determine Macro Risk Status
            if current_vix >= 30.0 or (not sp_trend_bullish and current_vix >= 25.0):
                regime = "DANGER"  # 하락/패닉장: 현금 100% 권장
            elif current_vix >= 22.0 or not sp_trend_bullish:
                regime = "CAUTION" # 주의/변동성 구간: 비중 축소 권장
            else:
                regime = "SAFE"    # 정상/상승 추세 구간

            return {
                "regime": regime,
                "vix": round(current_vix, 2),
                "vix_change_pct": round(vix_change, 2),
                "sp500_close": round(float(sp_current), 2),
                "sp500_bullish": sp_trend_bullish,
                "tnx_10y_yield": round(current_tnx, 2)
            }
        except Exception as e:
            print(f"[Warning] Failed to fetch macro indicators: {e}")
            return {
                "regime": "SAFE",
                "vix": 18.0,
                "vix_change_pct": 0.0,
                "sp500_close": 5000.0,
                "sp500_bullish": True,
                "tnx_10y_yield": 4.0
            }

    def fetch_stock_history(self, ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """
        Downloads OHLCV for a ticker and calculates essential quantitative features.
        """
        try:
            df = yf.Ticker(ticker).history(period=period)
            if df.empty or len(df) < 50:
                return None

            df = df.copy()
            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            # Moving Averages
            df['SMA_10'] = close.rolling(10).mean()
            df['SMA_20'] = close.rolling(20).mean()
            df['SMA_50'] = close.rolling(50).mean()
            df['SMA_200'] = close.rolling(200).mean()

            # Moving Average Slopes (Trend direction)
            df['SMA_20_SLOPE'] = (df['SMA_20'] - df['SMA_20'].shift(5)) / df['SMA_20'].shift(5)

            # RSI 14
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI_14'] = 100 - (100 / (1 + rs))

            # MACD (12, 26, 9)
            ema_12 = close.ewm(span=12, adjust=False).mean()
            ema_26 = close.ewm(span=26, adjust=False).mean()
            df['MACD'] = ema_12 - ema_26
            df['MACD_SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
            df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']

            # Bollinger Bands (20, 2)
            std_20 = close.rolling(20).std()
            df['BB_MID'] = df['SMA_20']
            df['BB_UPPER'] = df['BB_MID'] + 2 * std_20
            df['BB_LOWER'] = df['BB_MID'] - 2 * std_20
            df['BB_PCT_B'] = (close - df['BB_LOWER']) / (df['BB_UPPER'] - df['BB_LOWER'] + 1e-9)

            # Average True Range (ATR 14) for dynamic volatility stop-loss
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['ATR_14'] = tr.rolling(14).mean()
            df['ATR_RATIO'] = df['ATR_14'] / close

            # Volume Ratio (relative to 20-day average)
            df['VOL_RATIO'] = volume / (volume.rolling(20).mean() + 1e-9)

            # 52-Week (or period) High Distance
            rolling_high_250 = high.rolling(min(len(df), 250)).max()
            df['HIGH_DIST_PCT'] = (close - rolling_high_250) / rolling_high_250

            # Forward Returns for Training (next 5 days return)
            df['TARGET_5D_RETURN'] = close.shift(-5) / close - 1.0

            return df
        except Exception as e:
            print(f"[Warning] Failed to fetch data for {ticker}: {e}")
            return None
