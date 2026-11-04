import lightgbm as lgb
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from .base_model import BaseStockModel

class MomentumBreakoutModel(BaseStockModel):
    """
    Model A: Momentum & Breakout Strategy (LightGBM)
    Predicts stocks likely to break out with heavy volume and upward momentum.
    """
    def __init__(self):
        super().__init__(name="Model A [모멘텀 돌파형 (LightGBM)]")
        self.model = None
        self.feature_cols = [
            'SMA_20_SLOPE', 'RSI_14', 'MACD_HIST', 
            'BB_PCT_B', 'ATR_RATIO', 'VOL_RATIO', 'HIGH_DIST_PCT'
        ]

    def _prepare_training_data(self, historical_data: Dict[str, pd.DataFrame]):
        X_list, y_list = [], []
        for ticker, df in historical_data.items():
            if df is None or len(df) < 60:
                continue
            clean = df.dropna(subset=self.feature_cols + ['TARGET_5D_RETURN'])
            if len(clean) > 20:
                X_list.append(clean[self.feature_cols])
                # Target: 1 if 5-day return > 2%, 0 otherwise (momentum classification)
                y_list.append((clean['TARGET_5D_RETURN'] > 0.02).astype(int))

        if not X_list:
            return None, None
        return pd.concat(X_list, ignore_index=True), pd.concat(y_list, ignore_index=True)

    def fit(self, historical_data: Dict[str, pd.DataFrame]) -> None:
        X, y = self._prepare_training_data(historical_data)
        if X is None or len(X) < 100:
            return

        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'learning_rate': 0.05,
            'num_leaves': 15,
            'max_depth': 4,
            'min_child_samples': 20,
            'verbose': -1,
            'random_state': 42
        }
        train_data = lgb.Dataset(X, label=y)
        self.model = lgb.train(params, train_data, num_boost_round=100)

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
            
            # Predict probability using LightGBM if fitted, else heuristic
            if self.model is not None:
                features = pd.DataFrame([latest[self.feature_cols]])
                prob = float(self.model.predict(features)[0])
            else:
                # Heuristic fallback: strong RSI, positive slope, high volume
                score = 0.5
                if latest['RSI_14'] > 55: score += 0.15
                if latest['VOL_RATIO'] > 1.2: score += 0.15
                if latest['HIGH_DIST_PCT'] > -0.05: score += 0.1
                prob = min(0.95, score)

            # Filtering condition for momentum:
            # Price > SMA50 and RSI between 50 and 75
            if latest['Close'] > latest['SMA_50'] and 50 <= latest['RSI_14'] <= 75:
                # Stop loss: 2 * ATR below or 2.5% fixed
                stop_loss = round(max(current_price * 0.975, current_price - 1.8 * atr), 2)
                target_profit = round(current_price * 1.08, 2) # +8% initial target

                results.append({
                    "ticker": ticker,
                    "model": self.name,
                    "score": round(prob, 3),
                    "current_price": round(current_price, 2),
                    "stop_loss_price": stop_loss,
                    "stop_loss_pct": round(((stop_loss - current_price) / current_price) * 100, 2),
                    "target_price": target_profit,
                    "target_profit_pct": round(((target_profit - current_price) / current_price) * 100, 2),
                    "reason": f"신고가 대비 {round(latest['HIGH_DIST_PCT']*100, 1)}% 근접, 거래량 {round(latest['VOL_RATIO'], 1)}배, RSI {round(latest['RSI_14'], 1)}"
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results
