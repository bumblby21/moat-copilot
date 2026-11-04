import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import yfinance as yf

PORTFOLIO_FILE = Path(__file__).resolve().parent / "data" / "portfolio.json"
if not PORTFOLIO_FILE.parent.exists() or not PORTFOLIO_FILE.exists():
    p_alt = Path(__file__).resolve().parent / "portfolio.json"
    if p_alt.exists():
        PORTFOLIO_FILE = p_alt

class PortfolioTracker:
    """
    Tracks user's selected investments, monitors stop-loss/take-profit,
    and logs trade results to enable continuous AI learning & adaptation.
    """
    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not PORTFOLIO_FILE.exists():
            initial_data = {
                "balance_usd": 10000.0,
                "cash_usd": 10000.0,
                "open_positions": [],
                "closed_positions": [],
                "model_learning_stats": {
                    "Model A": {"wins": 0, "losses": 0, "cumulative_pnl": 0.0},
                    "Model B": {"wins": 0, "losses": 0, "cumulative_pnl": 0.0},
                    "Model C": {"wins": 0, "losses": 0, "cumulative_pnl": 0.0}
                }
            }
            with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2, ensure_ascii=False)

    def load(self) -> Dict[str, Any]:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: Dict[str, Any]):
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def check_and_process_weekly_deposit(self, deposit_usd: float = 50.0) -> Dict[str, Any]:
        """
        Processes weekly $50 deposit into available cash every 7 days.
        """
        data = self.load()
        today = datetime.now().date()
        last_date_str = data.get("last_weekly_deposit_date")

        if not last_date_str:
            data["last_weekly_deposit_date"] = today.strftime("%Y-%m-%d")
            self.save(data)
            return {"deposited": False, "days_until_next": 7}

        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        except Exception:
            last_date = today

        days_passed = (today - last_date).days

        if days_passed >= 7:
            data["cash_usd"] = round(data.get("cash_usd", 1000.0) + deposit_usd, 2)
            data["balance_usd"] = round(data.get("balance_usd", 1000.0) + deposit_usd, 2)
            data["last_weekly_deposit_date"] = today.strftime("%Y-%m-%d")
            self.save(data)
            return {
                "deposited": True,
                "amount_usd": deposit_usd,
                "new_cash": data["cash_usd"],
                "total_balance": data["balance_usd"],
                "days_passed": days_passed
            }

        return {"deposited": False, "days_until_next": 7 - days_passed}

    def add_positions(self, selected_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Records user's chosen stocks and amounts into the live portfolio.
        """
        data = self.load()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for trade in selected_trades:
            ticker = trade['ticker']
            amount_usd = trade['amount_usd']
            entry_price = trade['entry_price']
            stop_loss = trade['stop_loss_price']
            target_price = trade.get('target_price', entry_price * 1.08)
            models = trade.get('models', ['AI'])
            shares = round(amount_usd / entry_price, 2) if entry_price > 0 else 0.0

            position = {
                "id": f"{ticker}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "ticker": ticker,
                "entry_date": now_str,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss,
                "target_price": target_price,
                "amount_usd": amount_usd,
                "shares": shares,
                "recommending_models": models,
                "status": "OPEN"
            }
            data["open_positions"].append(position)
            data["cash_usd"] = max(0.0, data["cash_usd"] - amount_usd)

        self.save(data)
        return data

    def check_open_positions(self) -> Dict[str, Any]:
        """
        Daily check: fetches current prices of open positions,
        evaluates if stop-loss or take-profit triggered,
        and updates continuous learning memory.
        """
        data = self.load()
        open_pos = data.get("open_positions", [])
        if not open_pos:
            return {"active": [], "closed_today": []}

        tickers = list({p['ticker'] for p in open_pos})
        current_prices = {}
        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="2d")
                if not hist.empty:
                    current_prices[t] = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        still_open = []
        closed_today = []

        for pos in open_pos:
            t = pos['ticker']
            cur_p = current_prices.get(t, pos['entry_price'])
            pnl_pct = ((cur_p - pos['entry_price']) / pos['entry_price']) * 100
            pnl_usd = (cur_p - pos['entry_price']) * pos['shares']

            is_stop_loss = cur_p <= pos['stop_loss_price']
            is_take_profit = cur_p >= pos['target_price']

            if is_stop_loss or is_take_profit:
                reason = "손절선 터치 (-2.5%)" if is_stop_loss else "목표가 도달 익절 (+8%)"
                pos["exit_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                pos["exit_price"] = cur_p
                pos["pnl_pct"] = round(pnl_pct, 2)
                pos["pnl_usd"] = round(pnl_usd, 2)
                pos["close_reason"] = reason
                pos["status"] = "CLOSED"

                closed_today.append(pos)
                data["closed_positions"].append(pos)
                data["cash_usd"] += (pos["amount_usd"] + pnl_usd)

                # Continuous Learning Feedback: Update model stats
                is_win = pnl_pct > 0
                for m in pos.get("recommending_models", []):
                    m_key = "Model A" if "A" in m else ("Model B" if "B" in m else "Model C")
                    if m_key in data["model_learning_stats"]:
                        if is_win:
                            data["model_learning_stats"][m_key]["wins"] += 1
                        else:
                            data["model_learning_stats"][m_key]["losses"] += 1
                        data["model_learning_stats"][m_key]["cumulative_pnl"] += pnl_usd
            else:
                pos["current_price"] = cur_p
                pos["unrealized_pnl_pct"] = round(pnl_pct, 2)
                pos["unrealized_pnl_usd"] = round(pnl_usd, 2)
                still_open.append(pos)

        data["open_positions"] = still_open
        self.save(data)
        return {"active": still_open, "closed_today": closed_today}
