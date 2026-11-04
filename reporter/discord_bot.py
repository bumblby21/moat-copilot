import requests
import json
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from typing import Dict, List, Any
from datetime import datetime
import config

class DiscordReporter:
    """
    Sends structured, high-readability Discord reports with 3 separate cards,
    clean mobile-adapted formatting, Korean company names, and zero clutter.
    """
    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url

    def send_report(
        self,
        macro_state: Dict[str, Any],
        tournament_result: Dict[str, Any],
        rl_allocation: Dict[str, Any],
        unanimous_picks: List[Dict[str, Any]],
        total_budget_usd: float = 1000.0
    ) -> bool:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        regime = macro_state.get('regime', 'SAFE')
        vix = macro_state.get('vix', 18.0)
        
        # Color codes:
        c1_color = 0x27ae60 if regime == "SAFE" else (0xf39c12 if regime == "CAUTION" else 0xc0392b)
        c2_color = 0x2980b9
        c3_color = 0x16a085

        champion = tournament_result.get('champion', {})
        champ_name = champion.get('model_name', 'Model B')
        champ_sharpe = champion.get('sharpe_ratio', 1.28)
        champ_win = champion.get('win_rate', 57.8)
        champ_mdd = champion.get('mdd_pct', 21.3)

        # ==========================================
        # CARD 1: 글로벌 시장 진단 & 계좌 기조
        # ==========================================
        card1 = {
            "title": f"미국 주식 일일 브리핑 ({now_str})",
            "color": c1_color,
            "description": (
                f"### [1] 글로벌 매크로 & 계좌 자금 배분\n"
                f"```text\n"
                f"시장 상태       : {regime} (VIX: {vix})\n"
                f"미국 10년물 금리 : {macro_state.get('tnx_10y_yield', 4.95)}%\n"
                f"설정 운용 자산   : ${total_budget_usd:,.0f}\n"
                f"권장 현금 비중   : {rl_allocation.get('cash_pct', 20.0)}% (${rl_allocation.get('cash_usd', 200):,.0f})\n"
                f"실투자 배정액   : ${rl_allocation.get('total_invested_usd', 800):,.0f}\n"
                f"```\n"
                f"**운용 지침**: {rl_allocation.get('regime_comment', '정상 운용')}"
            )
        }

        # ==========================================
        # CARD 2: 모델 토너먼트 리그전 챔피언
        # ==========================================
        card2 = {
            "title": "모델 토너먼트 리그전 결과",
            "color": c2_color,
            "description": (
                f"### [2] 현재 1위 챔피언 모델\n"
                f"**{champ_name}**\n"
                f"```text\n"
                f"샤프 지수 (Sharpe) : {champ_sharpe}\n"
                f"과거 승률 (Win Rate): {champ_win}%\n"
                f"최대 낙폭 (MDD)    : {champ_mdd}%\n"
                f"수익-손실비 (PF)   : {champion.get('profit_factor', 1.6)}\n"
                f"```\n"
                f"*최근 백테스트에서 위험 대비 수익률이 가장 우수한 모델입니다.*"
            )
        }

        # ==========================================
        # CARD 3: 강화학습(RL) 추천 포트폴리오 & 손절선 (모바일 최적화)
        # ==========================================
        allocated_stocks = rl_allocation.get('allocated_stocks', [])
        
        # Build Mobile-Adapted Block List (No horizontal table wrapping!)
        stock_blocks = []
        links_markdown = []
        
        for idx, stock in enumerate(allocated_stocks[:6], start=1):
            ticker = stock['ticker']
            info = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": "우량주"})
            name = info["name"]
            desc = info["desc"]

            cur_p = stock['current_price']
            sl_p = stock['stop_loss_price']
            tp_p = stock.get('target_price', cur_p * 1.08)
            pct = stock['recommended_pct']
            usd = stock['recommended_usd']
            shares = round(usd / cur_p, 1) if cur_p > 0 else 0.0

            block = (
                f"[{idx}] {ticker} · {name} ({desc})\n"
                f"    현재가: ${cur_p:.2f} ──▶ 손절선: ${sl_p:.2f} (-2.5%)\n"
                f"    추천액: ${usd:.0f} ({shares:.1f}주, {pct:.1f}%) ──▶ 목표: ${tp_p:.2f}"
            )
            stock_blocks.append(block)
            links_markdown.append(f"• **[{ticker} ({name}) 차트보기](https://www.tradingview.com/symbols/{ticker}/)** : {stock.get('reason', '')}")

        blocks_str = "\n----------------------------------------\n".join(stock_blocks)
        links_str = "\n".join(links_markdown)

        # Consensus picks summary with Korean names
        consensus_text = ""
        if unanimous_picks:
            c_items = []
            for cp in unanimous_picks[:5]:
                t = cp['ticker']
                c_name = config.TICKER_INFO.get(t, {}).get("name", t)
                c_items.append(f"{t}({c_name})")
            consensus_text = f"**만장일치 공통 지목 종목**: `{', '.join(c_items)}`\n\n"

        card3 = {
            "title": "강화학습(RL) 추천 포트폴리오",
            "color": c3_color,
            "description": (
                f"### [3] 종목별 포지션 및 손절선\n"
                f"{consensus_text}"
                f"```text\n"
                f"{blocks_str}\n"
                f"```\n"
                f"**종목별 상세 및 차트 링크**\n"
                f"{links_str}"
            ),
            "footer": {
                "text": "Antigravity AI • 직접 선택 매수: 터미널에서 'python select_portfolio.py' 실행"
            }
        }

        # Send all 3 embeds in a single structured message
        payload = {
            "username": "AI 미국 주식 코파일럿",
            "embeds": [card1, card2, card3]
        }

        if self.webhook_url and self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            try:
                res = requests.post(self.webhook_url, json=payload, timeout=10)
                if res.status_code in [200, 204]:
                    print("[Discord] Successfully sent mobile-optimized report to Discord!")
                    return True
                else:
                    print(f"[Discord] Error: {res.status_code}, response: {res.text}")
                    return False
            except Exception as e:
                print(f"[Discord] Exception: {e}")
                return False
        return True
