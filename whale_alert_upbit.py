# -*- coding: utf-8 -*-
"""
업비트 고래 추종 알림(간단 트리거)
- 최근 체결(Trades)로 대량 체결/순매수 우위 감지
- 호가(Orderbook) 불균형 감지
- 신호 발생 시 ntfy 푸시

임계값 기본값 (고래급으로 높여놓음):
  LOOKBACK_SEC: 90초
  THRESH_NOTIONAL: 500,000,000원 (최근 누적 체결금액 5억 이상)
  THRESH_NET_BUY:  200,000,000원 (순매수 2억 이상)
  THRESH_OB_IMB:   500,000,000원 (호가 불균형 5억 이상)
"""
import os, time, requests

NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

MARKETS = [s.strip() for s in os.environ.get("MARKETS", "KRW-BTC,KRW-ETH").split(",") if s.strip()]
LOOKBACK_SEC = int(os.environ.get("LOOKBACK_SEC", "90"))

# ==== 고래급 임계값 기본 세팅 ====
THRESH_NOTIONAL = float(os.environ.get("THRESH_NOTIONAL", "500000000"))  # 5억
THRESH_NET_BUY  = float(os.environ.get("THRESH_NET_BUY",  "200000000"))  # 2억
THRESH_OB_IMB   = float(os.environ.get("THRESH_OB_IMB",   "500000000"))  # 5억
# =================================

UPBIT_TRADE_URL = "https://api.upbit.com/v1/trades/ticks"
UPBIT_OB_URL    = "https://api.upbit.com/v1/orderbook"

def send_push(title: str, body: str):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set; skip push"); return
    try:
        requests.post(
            f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={"Title": title},
            timeout=15
        )
    except Exception as e:
        print("ntfy push failed:", repr(e))

def get_recent_trades(market: str, count=200):
    r = requests.get(UPBIT_TRADE_URL, params={"market": market, "count": count}, timeout=10)
    r.raise_for_status()
    return r.json()

def get_orderbook(markets):
    r = requests.get(UPBIT_OB_URL, params={"markets": ",".join(markets)}, timeout=10)
    r.raise_for_status()
    return r.json()

def analyze_trades(market: str, lookback_sec: int):
    data = get_recent_trades(market)
    if not data:
        return 0.0, 0.0

    now_ms = int(time.time() * 1000)
    notional_sum = 0.0
    net_buy = 0.0

    for t in data:
        ts = t.get("timestamp")
        if ts is None or (now_ms - ts) > lookback_sec * 1000:
            continue
        price = float(t.get("trade_price", 0.0))
        vol   = float(t.get("trade_volume", 0.0))
        amt = price * vol
        notional_sum += amt
        if t.get("ask_bid") == "BID":
            net_buy += amt
        else:
            net_buy -= amt

    return notional_sum, net_buy

def analyze_orderbook(market: str):
    ob = get_orderbook([market])
    if not ob:
        return 0.0
    units = ob[0].get("orderbook_units", [])[:5]
    buy_amt = sum(u["bid_price"] * u["bid_size"] for u in units)
    sell_amt = sum(u["ask_price"] * u["ask_size"] for u in units)
    return buy_amt - sell_amt

def main():
    alerts = []
    for m in MARKETS:
        try:
            notional_sum, net_buy = analyze_trades(m, LOOKBACK_SEC)
            ob_imb = analyze_orderbook(m)

            signals = []
            if notional_sum >= THRESH_NOTIONAL:
                signals.append(f"대량체결 {notional_sum:,.0f}원↑")
            if net_buy >= THRESH_NET_BUY:
                signals.append(f"순매수우위 +{net_buy:,.0f}원")
            if ob_imb >= THRESH_OB_IMB:
                signals.append(f"호가불균형 +{ob_imb:,.0f}원")

            if signals:
                alerts.append(f"[{m}] " + " / ".join(signals))
        except Exception as e:
            print("err:", m, repr(e))

    if alerts:
        title = "업비트 고래 레이더"
        body = "\n".join(alerts)
        send_push(title, body)
    else:
        print("no whale signal")

if __name__ == "__main__":
    main()
