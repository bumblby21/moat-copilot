from sklearn.ensemble import GradientBoostingClassifier
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from .base_model import BaseStockModel

class MeanReversionModel(BaseStockModel):
    """
    Model B: Mean Reversion / Dip-Buying Strategy (Gradient Boosting)
    Targets high-quality stocks in overall uptrends experiencing temporary pullbacks near key supports.
    """
    def __init__(self):
        super().__init__(name="Model B [우량주 눌림목 반등형 (GBM)]")
        self.model = GradientBoostingClassifier(n_estimators=80, max_depth=3, random_state=42)
        self.is_fitted = False
        self.feature_cols = [
            'RSI_14', 'BB_PCT_B', 'ATR_RATIO', 
            'SMA_20_SLOPE', 'MACD_HIST'
        ]

    def _prepare_training_data(self, historical_data: Dict[str, pd.DataFrame]):
        X_list, y_list = [], []
        for ticker, df in historical_data.items():
            if df is None or len(df) < 60:
                continue
            clean = df.dropna(subset=self.feature_cols + ['TARGET_5D_RETURN'])
            # Filter condition: Pullback scenario (RSI < 50 or BB_PCT_B < 0.4)
            pullback_mask = (clean['RSI_14'] < 50) | (clean['BB_PCT_B'] < 0.4)
            clean_sub = clean[pullback_mask]
            if len(clean_sub) > 10:
                X_list.append(clean_sub[self.feature_cols])
                # Target: 1 if bounce back > 2% in next 5 days
                y_list.append((clean_sub['TARGET_5D_RETURN'] > 0.02).astype(int))

        if not X_list:
            return None, None
        return pd.concat(X_list, ignore_index=True), pd.concat(y_list, ignore_index=True)

    def fit(self, historical_data: Dict[str, pd.DataFrame]) -> None:
        X, y = self._prepare_training_data(historical_data)
        if X is not None and len(X) > 50 and len(y.unique()) > 1:
            self.model.fit(X, y)
            self.is_fitted = True

    def score_stocks(self, current_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        results = []
        for ticker, df in current_data.items():
            if df is None or len(df) < 30:
                continue
            latest = df.iloc[-1]
            if pd.isna(latest['Close']):
                continue

            current_price = float(latest['Close'])
            atr = float(latest['ATR_14']) if not pd.isna(latest['ATR_14']) else current_price * 0.025

            # Long-term trend must be bullish (Price > SMA200 or SMA50)
            long_term_bullish = latest['Close'] > latest['SMA_200'] or latest['Close'] > latest['SMA_50']
            # Short-term dip: RSI between 30 and 48 OR BB_PCT_B < 0.35
            is_dip = (30 <= latest['RSI_14'] <= 48) or (latest['BB_PCT_B'] < 0.35)

            if long_term_bullish and is_dip:
                if self.is_fitted:
                    features = pd.DataFrame([latest[self.feature_cols]])
                    prob = float(self.model.predict_proba(features)[0][1])
                else:
                    # Heuristic score for dip: lower RSI with positive slope
                    prob = 0.65 + (45 - latest['RSI_14']) * 0.01

                stop_loss = round(max(current_price * 0.97, current_price - 1.5 * atr), 2)
                target_profit = round(current_price * 1.07, 2) # +7% bounce target

                results.append({
                    "ticker": ticker,
                    "model": self.name,
                    "score": round(min(0.95, prob), 3),
                    "current_price": round(current_price, 2),
                    "stop_loss_price": stop_loss,
                    "stop_loss_pct": round(((stop_loss - current_price) / current_price) * 100, 2),
                    "target_price": target_profit,
                    "target_profit_pct": round(((target_profit - current_price) / current_price) * 100, 2),
                    "reason": f"장기 우상향 중 단기 눌림목 발생 (RSI {round(latest['RSI_14'], 1)}, 볼린저밴드 하단 {round(latest['BB_PCT_B'], 2)})"
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results
