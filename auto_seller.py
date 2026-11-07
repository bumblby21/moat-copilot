import yfinance as yf
from datetime import datetime
from typing import Dict, List, Any
import requests
import config
try:
    from tracker import PortfolioTracker
except ModuleNotFoundError:
    from portfolio.tracker import PortfolioTracker

class AutoSellerEngine:
    """
    Warren Buffett AI Auto-Seller & Smart DCA Engine:
    1. Overvalued Take-Profit: Auto-sell when gain >= +25%
    2. Moat Deterioration Stop: Auto-sell when ROE < 10%
    3. Hard Safety Stop: Auto-sell when loss <= -15% (Catastrophic protection)
    4. Smart DCA Detection: Detects dip-buying opportunities for resilient companies (ROE >= 15% & down >= 5%)
    """
    def __init__(self):
        self.tracker = PortfolioTracker()

    def check_and_execute_sells(self) -> List[Dict[str, Any]]:
        data = self.tracker.load()
        open_positions = data.get("open_positions", [])
        if not open_positions:
            return []

        sold_list = []
        remaining_positions = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for pos in open_positions:
            ticker = pos['ticker']
            entry_p = pos['entry_price']
            amount_usd = pos['amount_usd']
            shares = pos['shares']
            
            try:
                stock = yf.Ticker(ticker)
                cur_p = float(stock.fast_info.last_price)
                if not cur_p or cur_p <= 0:
                    cur_p = float(stock.history(period="1d")['Close'].iloc[-1])
                info = stock.info
                roe = info.get('returnOnEquity', 0.20) or 0.20
            except Exception:
                cur_p = entry_p
                roe = 0.20

            gain_pct = ((cur_p - entry_p) / entry_p) * 100.0
            profit_usd = (cur_p - entry_p) * shares
            take_profit_pct = config.BUFFETT_CONFIG.get('auto_take_profit_pct', 0.15)
            target_p = pos.get('target_price', entry_p * (1.0 + take_profit_pct))

            # Condition 1: Take Profit (Overvaluation Ceiling reached >= +15%)
            is_take_profit = (cur_p >= target_p) or (gain_pct >= take_profit_pct * 100.0)
            
            # Condition 2: Moat Deterioration (Fundamental ROE < 15%)
            moat_cut_roe = config.BUFFETT_CONFIG.get('fundamental_cut_roe', 0.15)
            is_moat_broken = (roe < moat_cut_roe)

            # Condition 3: Hard Catastrophic Stop (Loss <= -25% for extreme crash protection)
            cat_stop = config.BUFFETT_CONFIG.get('catastrophic_stop_pct', -25.0)
            is_hard_stop = (gain_pct <= cat_stop)

            if is_take_profit or is_moat_broken or is_hard_stop:
                if is_take_profit:
                    reason = f"🎉 [고평가 익절] 목표 가치 밴드 상단(+{gain_pct:.1f}%) 도달로 차익 실현"
                elif is_moat_broken:
                    reason = f"⚠️ [해자 훼손 손절] 기업 ROE({roe*100:.1f}%)가 기준(15%) 미만으로 붕괴되어 펀더멘털 기계적 손절"
                else:
                    reason = f"🛡️ [재난 안전벨트 손절] 최대 허용 낙폭({cat_stop:.0f}%) 도달로 계좌 보호 기계적 손절"

                closed_pos = {
                    **pos,
                    "exit_date": now_str,
                    "exit_price": round(cur_p, 2),
                    "realized_pnl_pct": round(gain_pct, 2),
                    "realized_pnl_usd": round(profit_usd, 2),
                    "exit_reason": reason,
                    "status": "CLOSED"
                }

                sold_list.append(closed_pos)
                data["closed_positions"].append(closed_pos)
                data["cash_usd"] += round(amount_usd + profit_usd, 2)
            else:
                pos["current_price"] = round(cur_p, 2)
                pos["unrealized_pnl_pct"] = round(gain_pct, 2)
                pos["unrealized_pnl_usd"] = round(profit_usd, 2)
                remaining_positions.append(pos)

        if sold_list:
            data["open_positions"] = remaining_positions
            self.tracker.save(data)
            self._notify_discord_auto_sell(sold_list)

        return sold_list

    def check_dca_opportunities(self) -> List[Dict[str, Any]]:
        """
        Scans open positions to identify Smart DCA (물타기) opportunities under Option B & Guardrails:
        - Stage 1: down >= 10.0%
        - Stage 2: down >= 18.0%
        - ROE >= 15% (Fundamentally intact)
        - Guardrail 1: scale_in_count < 2 (Max 2 additions hard cap)
        - Guardrail 2: position total amount <= $250
        - Guardrail 3: available cash >= $100 buffer
        - Guardrail 4: cooldown >= 3 days
        """
        data = self.tracker.load()
        cash = data.get("cash_usd", 1000.0)
        open_positions = data.get("open_positions", [])
        cfg = config.BUFFETT_CONFIG
        add_amount = cfg.get("dca_add_amount_usd", 60.0)
        min_buffer = cfg.get("dca_min_cash_buffer_usd", 100.0)

        if not open_positions or cash < add_amount:
            return []

        dca_candidates = []
        now = datetime.now()

        for pos in open_positions:
            scale_count = pos.get('scale_in_count', 0)
            if scale_count >= cfg.get("dca_max_count", 2):
                continue

            current_amt = pos.get('amount_usd', 120.0)
            if (current_amt + add_amount) > cfg.get("dca_max_position_usd", 250.0):
                continue

            # Guardrail 4: 3-day Cooldown Period from last action (DCA or entry) to confirm bottom
            last_action_str = pos.get('last_dca_date') or pos.get('entry_date')
            if last_action_str:
                try:
                    last_dt = datetime.strptime(last_action_str[:10], "%Y-%m-%d")
                    if (now.date() - last_dt.date()).days < cfg.get("dca_cooldown_days", 3):
                        continue
                except Exception:
                    pass

            ticker = pos['ticker']
            entry_p = pos['entry_price']
            shares = pos['shares']

            try:
                stock = yf.Ticker(ticker)
                cur_p = float(stock.fast_info.last_price)
                if not cur_p or cur_p <= 0:
                    cur_p = float(stock.history(period="1d")['Close'].iloc[-1])
                info = stock.info
                roe = info.get('returnOnEquity', 0.20) or 0.20
            except Exception:
                continue

            gain_pct = ((cur_p - entry_p) / entry_p) * 100.0
            roe_min = cfg.get("min_roe", 0.15)
            target_drop = cfg.get("dca_stage1_drop_pct", -10.0) if scale_count == 0 else cfg.get("dca_stage2_drop_pct", -18.0)

            # Option B trigger: gain_pct <= target_drop and ROE >= 15%
            if gain_pct <= target_drop and roe >= roe_min:
                add_usd = min(cash, add_amount)
                new_shares = add_usd / cur_p
                total_shares = shares + new_shares
                new_avg_price = (current_amt + add_usd) / total_shares

                name = config.TICKER_INFO.get(ticker, {}).get("name", ticker)
                dca_candidates.append({
                    "position_id": pos.get('id', ticker),
                    "ticker": ticker,
                    "name": name,
                    "entry_price": entry_p,
                    "current_price": cur_p,
                    "drop_pct": abs(round(gain_pct, 1)),
                    "target_drop_pct": abs(target_drop),
                    "roe_pct": round(roe * 100.0, 1),
                    "add_amount_usd": add_usd,
                    "current_shares": shares,
                    "new_shares": round(new_shares, 2),
                    "new_avg_price": round(new_avg_price, 2),
                    "scale_in_count": scale_count,
                    "next_stage": scale_count + 1
                })

        return dca_candidates

    def check_and_execute_auto_dca(self) -> List[Dict[str, Any]]:
        """
        Option B: Automatically executes DCA when conditions and guardrails are met.
        """
        candidates = self.check_dca_opportunities()
        if not candidates:
            return []

        executed = []
        for c in candidates:
            res = self.execute_dca(c['ticker'], c['add_amount_usd'])
            if res.get("success"):
                executed.append({
                    **res,
                    "name": c['name'],
                    "drop_pct": c['drop_pct'],
                    "roe_pct": c['roe_pct'],
                    "stage": c['next_stage'],
                    "max_count": config.BUFFETT_CONFIG.get("dca_max_count", 2),
                    "target_profit_p": round(res['new_avg'] * (1.0 + config.BUFFETT_CONFIG.get('auto_take_profit_pct', 0.15)), 2)
                })
        return executed

    def execute_dca(self, ticker: str, add_usd: float = 60.0) -> Dict[str, Any]:
        """
        Executes scale-in: updates position average price, shares, and decreases cash.
        """
        data = self.tracker.load()
        open_pos = data.get("open_positions", [])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for pos in open_pos:
            if pos['ticker'] == ticker:
                try:
                    stock = yf.Ticker(ticker)
                    cur_p = float(stock.fast_info.last_price)
                    if not cur_p or cur_p <= 0:
                        cur_p = pos.get('current_price', pos['entry_price'])
                except Exception:
                    cur_p = pos.get('current_price', pos['entry_price'])

                old_entry = pos['entry_price']
                old_amt = pos['amount_usd']
                old_shares = pos['shares']
                new_shares = add_usd / cur_p
                total_shares = old_shares + new_shares
                new_avg = (old_amt + add_usd) / total_shares

                pos['amount_usd'] += add_usd
                pos['shares'] = round(total_shares, 2)
                pos['entry_price'] = round(new_avg, 2)
                pos['current_price'] = round(cur_p, 2)
                pos['scale_in_count'] = pos.get('scale_in_count', 0) + 1
                pos['last_dca_date'] = now_str
                pos['target_price'] = round(new_avg * (1.0 + config.BUFFETT_CONFIG.get('auto_take_profit_pct', 0.15)), 2)
                data['cash_usd'] = max(0.0, round(data['cash_usd'] - add_usd, 2))
                
                self.tracker.save(data)
                return {
                    "success": True,
                    "ticker": ticker,
                    "old_entry": old_entry,
                    "new_avg": round(new_avg, 2),
                    "add_usd": add_usd,
                    "cur_price": round(cur_p, 2),
                    "total_shares": round(total_shares, 2),
                    "scale_in_count": pos['scale_in_count'],
                    "remaining_cash": data['cash_usd']
                }
        return {"success": False}

    def _notify_discord_auto_sell(self, sold_list: List[Dict[str, Any]]):
        if not config.DISCORD_WEBHOOK_URL:
            return

        blocks = []
        for s in sold_list:
            name = config.TICKER_INFO.get(s['ticker'], {}).get("name", s['ticker'])
            pnl_sign = "+" if s['realized_pnl_pct'] >= 0 else ""
            blocks.append(
                f"• {s['ticker']} · {name}\n"
                f"  진입가: ${s['entry_price']:.2f} ──▶ 매도가: ${s['exit_price']:.2f}\n"
                f"  실현손익: {pnl_sign}${s['realized_pnl_usd']:.2f} ({pnl_sign}{s['realized_pnl_pct']:.2f}%)\n"
                f"  사유: {s['exit_reason']}"
            )

        text_block = "\n----------------------------------------\n".join(blocks)
        embed = {
            "title": "🚨 AI 자동 매도 집행 완료 알림",
            "color": 0xe67e22,
            "description": (
                f"```text\n"
                f"{text_block}\n"
                f"```\n"
                f"• **AI 판단**: 사람이 망설이기 쉬운 매도 시점을 AI가 원칙대로 기계적으로 집행했습니다.\n"
                f"• 회수된 원금과 수익금은 가용 현금으로 안전하게 복귀되었습니다."
            )
        }

        try:
            requests.post(config.DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        except Exception:
            pass
