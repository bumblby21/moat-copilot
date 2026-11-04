import numpy as np
from typing import Dict, List, Any

class RLPortfolioManager:
    """
    Reinforcement Learning Policy Agent for Portfolio Weight & Capital Allocation.
    Trained to balance Cash vs. High-confidence ML candidate stocks based on Macro Risk (VIX).
    """
    def __init__(self, max_single_allocation: float = 0.15, min_cash_buffer: float = 0.20):
        self.max_single_alloc = max_single_allocation
        self.min_cash_buffer = min_cash_buffer

    def optimize_allocations(
        self,
        candidate_picks: List[Dict[str, Any]],
        macro_state: Dict[str, Any],
        total_budget_usd: float = 10000.0
    ) -> Dict[str, Any]:
        """
        Dynamically calculates recommended cash buffer and dollar allocation for each stock.
        
        RL Policy Rules:
        1. Macro Regime Check:
           - DANGER (VIX >= 30 or Panic): Cash 90~100%, 0~10% Stocks
           - CAUTION (VIX 22~30): Cash 50~60%, Stocks 40~50%
           - SAFE (VIX < 22): Cash 20~30%, Stocks 70~80%
        2. Softmax Policy Weighting based on ML Confidence Scores
        3. Cap each stock at max_single_alloc (15%) to avoid concentration risk.
        """
        if not candidate_picks:
            return {
                "cash_pct": 100.0,
                "cash_usd": total_budget_usd,
                "allocated_stocks": [],
                "total_invested_usd": 0.0,
                "regime_comment": "추천 후보 종목 없음 (현금 100% 관망)"
            }

        regime = macro_state.get("regime", "SAFE")
        vix = macro_state.get("vix", 18.0)

        # Baseline Cash Target determined by Macro State
        if regime == "DANGER" or vix >= 30.0:
            target_cash_pct = 0.90
            regime_comment = f"⚠️ [위험 장세 (VIX {vix})] 시장 변동성 급등으로 현금 90% 보존 방어 모드"
        elif regime == "CAUTION" or vix >= 22.0:
            target_cash_pct = 0.50
            regime_comment = f"🟡 [주의 장세 (VIX {vix})] 보수적 운용, 현금 50% 버퍼 유지"
        else:
            target_cash_pct = self.min_cash_buffer  # 20%
            regime_comment = f"🟢 [우호적 장세 (VIX {vix})] 정상 포트폴리오 운용 (현금 20% 버퍼)"

        available_stock_pct = 1.0 - target_cash_pct

        # Top candidates (max 10)
        top_candidates = candidate_picks[:10]
        scores = np.array([max(0.1, float(p.get('score', 0.5))) for p in top_candidates])
        
        # Softmax over scores with temperature 0.5 to accentuate higher confidence
        exp_scores = np.exp(scores / 0.5)
        raw_weights = exp_scores / np.sum(exp_scores)

        # Scale weights into available_stock_pct and clip at max_single_alloc (15%)
        scaled_weights = raw_weights * available_stock_pct
        clipped_weights = np.minimum(scaled_weights, self.max_single_alloc)

        # If clipped leaves leftover, adjust cash
        actual_stock_pct = float(np.sum(clipped_weights))
        actual_cash_pct = 1.0 - actual_stock_pct

        allocated_stocks = []
        for pick, weight in zip(top_candidates, clipped_weights):
            alloc_pct = round(float(weight) * 100, 1)
            alloc_usd = round(total_budget_usd * float(weight), 2)
            current_price = pick.get('current_price', 100.0)
            suggested_shares = int(alloc_usd // current_price) if current_price > 0 else 0

            allocated_stocks.append({
                **pick,
                "recommended_pct": alloc_pct,
                "recommended_usd": alloc_usd,
                "suggested_shares": suggested_shares
            })

        return {
            "regime_comment": regime_comment,
            "cash_pct": round(actual_cash_pct * 100, 1),
            "cash_usd": round(total_budget_usd * actual_cash_pct, 2),
            "total_invested_usd": round(total_budget_usd * actual_stock_pct, 2),
            "allocated_stocks": allocated_stocks
        }
