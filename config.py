import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ==========================================
# 1. Notification (Discord Webhook & Bot)
# ==========================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# ==========================================
# 2. Alpaca Paper Trading (Optional)
# ==========================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# ==========================================
# 3. Warren Buffett Moat & Value Universe (버핏 30대 해자 기업)
# ==========================================
DEFAULT_TICKERS = [
    # Buffett Core Holdings
    "AAPL", "KO", "AXP", "CVX", "BAC", "OXY", "MCO", "KHC",
    # Monopoly Payment & Tech Moats
    "V", "MA", "MSFT", "GOOGL",
    # Consumer Monopolies & Strong Brands (과매도 가치주)
    "NKE", "SBUX", "MCD", "PG", "PEP", "COST", "WMT", "DIS",
    # Healthcare & Defensive Cash Cows
    "JNJ", "ABBV", "PFE", "UNH",
    # Industrials & Energy
    "CAT", "UPS", "XOM"
]

# 한글 기업명 및 독점적 경제적 해자(Moat) 핵심 요약
TICKER_INFO = {
    "AAPL": {"name": "애플", "desc": "버핏 포트폴리오 1위 독점 생태계"},
    "KO": {"name": "코카콜라", "desc": "버핏이 35년 넘게 보유한 소비재 독점"},
    "AXP": {"name": "아메리칸익스프레스", "desc": "부유층 신용카드 과점 해자"},
    "CVX": {"name": "셰브론", "desc": "워런 버핏 보유 미국 2대 정유/에너지"},
    "BAC": {"name": "뱅크오브아메리카", "desc": "버핏 보유 미국 2위 상업은행"},
    "OXY": {"name": "옥시덴탈", "desc": "버핏이 지분을 지속 매집 중인 셰일오일"},
    "MCO": {"name": "무디스", "desc": "글로벌 신용평가 과점 독점력"},
    "KHC": {"name": "크래프트하인즈", "desc": "글로벌 대표 케첩/가공식품"},
    "V": {"name": "비자", "desc": "전 세계 결제 수수료 독점 네트워크"},
    "MA": {"name": "마스터카드", "desc": "글로벌 2대 카드 결제 독점망"},
    "MSFT": {"name": "마이크로소프트", "desc": "기업 소프트웨어/클라우드 독점 해자"},
    "GOOGL": {"name": "알파벳(구글)", "desc": "검색·유튜브 글로벌 광고 독점"},
    "NKE": {"name": "나이키", "desc": "글로벌 1위 스포츠 브랜드 (저점 매력)"},
    "SBUX": {"name": "스타벅스", "desc": "글로벌 커피 체인 독점 (바닥권)"},
    "MCD": {"name": "맥도날드", "desc": "글로벌 1위 패스트푸드 및 부동산"},
    "PG": {"name": "프록터앤갬블", "desc": "질레트·다우니 등 필수소비재 1위"},
    "PEP": {"name": "펩시코", "desc": "스낵(레이즈/도리토스) 및 음료 독점"},
    "COST": {"name": "코스트코", "desc": "멤버십 구독 기반 창고형 할인점 1위"},
    "WMT": {"name": "월마트", "desc": "미국 최대 오프라인 유통 공룡"},
    "DIS": {"name": "디즈니", "desc": "100년 IP 마블·테마파크 독점"},
    "JNJ": {"name": "존슨앤존슨", "desc": "60년 연속 배당 성장 헬스케어"},
    "ABBV": {"name": "애브비", "desc": "글로벌 면역/바이오 의약품 선두"},
    "PFE": {"name": "화이자", "desc": "글로벌 대형 제약사 (역사적 저점)"},
    "UNH": {"name": "유나이티드헬스", "desc": "미국 1위 건강보험/의료서비스"},
    "CAT": {"name": "캐터필러", "desc": "글로벌 건설/광산 중장비 1위"},
    "UPS": {"name": "UPS", "desc": "글로벌 물류 배송 과점"},
    "XOM": {"name": "엑슨모빌", "desc": "미국 최대 종합 에너지 공룡"}
}

# ==========================================
# 4. 버핏 가치투자 & 자금 설정 ($1,000 기준)
# ==========================================
DEFAULT_BUDGET_USD = 1000.0

BUFFETT_CONFIG = {
    # 최소 ROE 기준 (자기자본이익률 15% 이상)
    "min_roe": 0.15,
    # 최소 안전마진 (52주 고점 대비 최소 -10% 이상 할인)
    "min_discount_pct": 0.10,
    # 분할 매수 기본 비중 (종목당 $100~$150 내외)
    "position_size_pct": 0.15,
    # 고평가 자동 익절 목표 (진입가 대비 +15% 또는 밸류 상단 도달 시)
    "auto_take_profit_pct": 0.15,
    # 펀더멘털 훼손 손절 기준 (ROE 15% 미만 추락 시 기계적 손절)
    "fundamental_cut_roe": 0.15,
    # 최후 비상 안전벨트 손절 기준 (재난적 하락 방어 -25%)
    "catastrophic_stop_pct": -25.0,

    # ==========================================
    # B안 스마트 물타기 & 안전 방지책 (Guardrails)
    # ==========================================
    # 1차 추가 매수 기준: 진입가 대비 -10% 하락 시
    "dca_stage1_drop_pct": -10.0,
    # 2차 추가 매수 기준: 진입가 대비 -18% 하락 시
    "dca_stage2_drop_pct": -18.0,
    # 1회당 추가 매수 금액: $60
    "dca_add_amount_usd": 60.0,
    # 방지책 1: 종목당 최대 추가 매수 횟수 (2회 절대 캡)
    "dca_max_count": 2,
    # 방지책 2: 종목당 총 투자액 상한선 ($250, 계좌의 25% 이내)
    "dca_max_position_usd": 250.0,
    # 방지책 3: 최소 비상 현금 보존 버퍼 ($100 유지)
    "dca_min_cash_buffer_usd": 100.0,
    # 방지책 4: 동일 종목 추가 매수 간 쿨다운 기간 (최소 3일)
    "dca_cooldown_days": 3,
    # 주간 자동 적립식 충전금 ($50)
    "weekly_deposit_usd": 50.0
}
