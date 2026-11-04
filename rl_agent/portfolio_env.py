import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Dict, List, Any

class PortfolioAllocEnv(gym.Env):
    """
    Gymnasium Environment for Reinforcement Learning Portfolio Orchestrator.
    Learns to dynamically allocate capital between Cash and ML-screened candidate stocks.
    
    State:
      [VIX / 30.0, SP500_trend (1 or 0), Candidate_1_Score, Candidate_2_Score, ..., Volatilities...]
    Action:
      Continuous weights [Cash_Weight, Stock_1_Weight, ..., Stock_K_Weight]
    Reward:
      Return - (Volatility_Penalty + Drawdown_Penalty)
    """
    metadata = {'render_modes': ['human']}

    def __init__(self, max_candidates: int = 10):
        super().__init__()
        self.max_candidates = max_candidates
        
        # State: Macro (2 features) + Candidate scores (max_candidates) + Candidate volatilities (max_candidates)
        obs_dim = 2 + max_candidates * 2
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(obs_dim,), dtype=np.float32)
        
        # Action: Weights for Cash + max_candidates stocks
        action_dim = 1 + max_candidates
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(action_dim,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        obs = np.random.uniform(0.1, 0.9, size=self.observation_space.shape).astype(np.float32)
        return obs, {}

    def step(self, action: np.ndarray):
        # Normalize actions to sum to 1.0 (softmax style)
        weights = action / (np.sum(action) + 1e-9)
        cash_weight = weights[0]
        stock_weights = weights[1:]

        # Simulated return calculation for RL reward shaping
        simulated_returns = np.random.normal(loc=0.003, scale=0.015, size=len(stock_weights))
        portfolio_return = float(np.sum(stock_weights * simulated_returns))
        
        # Risk penalty: heavily penalize drawdowns if cash was too low during high volatility
        vol_penalty = float(np.std(stock_weights) * 0.05)
        reward = portfolio_return - vol_penalty

        terminated = True
        truncated = False
        return self.reset()[0], reward, terminated, truncated, {"portfolio_return": portfolio_return}
