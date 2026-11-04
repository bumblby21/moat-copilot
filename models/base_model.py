from abc import ABC, abstractmethod
from typing import Dict, List, Any
import pandas as pd

class BaseStockModel(ABC):
    """
    Abstract base class for all competing stock recommendation models.
    """
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def fit(self, historical_data: Dict[str, pd.DataFrame]) -> None:
        """
        Train the model using historical data across universe tickers.
        historical_data: Dict mapping ticker -> DataFrame with technical features
        """
        pass

    @abstractmethod
    def score_stocks(self, current_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Evaluate current market state and score/rank candidate tickers.
        Returns a sorted list of recommendations:
        [
            {
                'ticker': 'NVDA',
                'model': 'Model A - Momentum',
                'score': 0.85,          # 0.0 ~ 1.0 confidence score
                'current_price': 120.5,
                'stop_loss_price': 117.0,
                'target_price': 130.0,
                'reason': '신고가 근접 & 거래량 폭발'
            },
            ...
        ]
        """
        pass
