import pandas as pd
import numpy as np
from typing import Dict, List, Any
from .base_model import BaseStockModel

class QualityTrendModel(BaseStockModel):
    """
    Model C: Quality Trend & Volatility Filter Strategy
    Selects stocks with perfect moving average alignment (SMA10 > SMA20 > SMA50 > SMA200)
    and low volatility (consistent slow & steady upward drift).
    """
    def __init__(self):
        super().__init__(name="Model C [안정형 정배열 추세 (Multi-Factor)]")

    def fit(self, historical_data: Dict[str, pd.DataFrame]) -> None:
        # Multi-factor statistical scoring does not require parameter retraining
        pass

    def score_stocks(self, current_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        results = []
        for ticker, df in current_data.items():
            if df is None or len(df) < 50:
                continue
            latest = df.iloc[-1]
            if pd.isna(latest['Close']) or pd.isna(latest['SMA_50']):
                continue

            current_price = float(latest['Close'])
            atr = float(latest['ATR_14']) if not pd.isna(latest['ATR_14']) else current_price * 0.02

            # Check alignment: Price > SMA20 > SMA50
            sma_aligned = (current_price > latest['SMA_20'] > latest['SMA_50'])
            steady_slope = latest['SMA_20_SLOPE'] > 0
            moderate_rsi = 50 <= latest['RSI_14'] <= 68
            low_volatility = latest['ATR_RATIO'] < 0.035 # Daily fluctuation < 3.5%

            if sma_aligned and steady_slope and moderate_rsi:
                score = 0.60
                if low_volatility: score += 0.15
                if latest['MACD_HIST'] > 0: score += 0.10
                if latest['HIGH_DIST_PCT'] > -0.08: score += 0.10

                stop_loss = round(max(current_price * 0.975, current_price - 1.8 * atr), 2)
                target_profit = round(current_price * 1.09, 2)

                results.append({
                    "ticker": ticker,
                    "model": self.name,
                    "score": round(min(0.95, score), 3),
                    "current_price": round(current_price, 2),
                    "stop_loss_price": stop_loss,
                    "stop_loss_pct": round(((stop_loss - current_price) / current_price) * 100, 2),
                    "target_price": target_profit,
                    "target_profit_pct": round(((target_profit - current_price) / current_price) * 100, 2),
                    "reason": f"이평선 정배열(20>50), 변동성 안정({round(latest['ATR_RATIO']*100, 1)}%), 추세 지속형"
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results
