# -*- coding: utf-8 -*-
import os, textwrap, datetime, requests
import feedparser

# -------- 해외(영문) & 국내(국문) 피드 --------
FEEDS_EN = [
    "https://www.ft.com/rss/home",                                  # Financial Times
    "https://www.economist.com/finance-and-economics/rss.xml",      # The Economist - Finance & economics
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",                  # WSJ World
    "https://feeds.reuters.com/reuters/businessNews",               # Reuters Business
]

FEEDS_KR = [
    "https://www.yna.co.kr/economy/all-feed",       # 연합뉴스 경제(전체) RSS
    "https://www.hankyung.com/feed",                # 한국경제 메인 RSS
    "https://www.mk.co.kr/rss/30100041/30100000000000.xml",  # 매일경제 경제 일반
    # 필요하면 더 추가 가능
]

MAX_PER_FEED_EN = int(os.environ.get("MAX_PER_FEED_EN", "3"))
MAX_PER_FEED_KR = int(os.environ.get("MAX_PER_FEED_KR", "5"))
TOTAL_MAX_EN = int(os.environ.get("TOTAL_MAX_EN", "10"))
TOTAL_MAX_KR = int(os.environ.get("TOTAL_MAX_KR", "12"))

# ntfy (폰 푸시)
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")   # 예: jusun-econ-daily-9am-7b3f9f

# -------- 번역(영→한) --------
def translate_ko(text: str) -> str:
    if not text:
        return ""
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        try:
            from googletrans import Translator
            t = Translator()
            return t.translate(text, dest="ko").text
        except Exception:
            return text  # 실패하면 원문 유지

# -------- 유틸 --------
def strip_html(html_text: str) -> str:
    import re
    return re.sub("<[^<]+?>", "", html_text or "").strip()

def get_entries(feeds, per_feed, total_max):
    items = []
    for url in feeds:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:per_feed]:
                title = getattr(e, "title", "(no title)") or "(no title)"
                link = getattr(e, "link", "") or ""
                summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
                if summary:
                    summary = textwrap.shorten(strip_html(summary), width=280, placeholder="…")
                items.append({"title": title, "link": link, "summary": summary})
        except Exception as ex:
            print("feed error:", url, repr(ex))
    return items[:total_max]

def build_text(items, translate=False):
    lines = []
    for i, it in enumerate(items, 1):
        title = translate_ko(it["title"]) if translate else it["title"]
        summ = translate_ko(it["summary"]) if (translate and it["summary"]) else it["summary"]
        lines.append(f"{i}. {title}")
        if summ:
            lines.append(f" - {summ}")
        if it["link"]:
            lines.append(it["link"])
        lines.append("")
    return "\n".join(lines).strip()

def chunk_text(s: str, max_len: int):
    lines = (s or "").splitlines()
    chunks, cur = [], ""
    for line in lines:
        add = (line + "\n")
        if len(cur) + len(add) > max_len and cur:
            chunks.append(cur.rstrip())
            cur = add
        else:
            cur += add
    if cur:
        chunks.append(cur.rstrip())
    return chunks or ["(empty)"]

def send_push(title: str, body: str):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set; skip push"); return
    for idx, ch in enumerate(chunk_text(body, 1500), 1):
        t = title if idx == 1 and len(body) <= 1500 else f"{title} ({idx})"
        try:
            requests.post(
                f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}",
                data=ch.encode("utf-8"),
                headers={"Title": t},
                timeout=20
            )
        except Exception as e:
            print("ntfy push failed:", repr(e))

def main():
    # 오늘 날짜(한국시간)
    kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    date_str = kst.strftime("%Y-%m-%d")

    # 해외 기사: EN 원문 + KO 번역
    en_items = get_entries(FEEDS_EN, MAX_PER_FEED_EN, TOTAL_MAX_EN)
    if en_items:
        en_text = build_text(en_items, translate=False)
        ko_text = build_text(en_items, translate=True)
        send_push(f"{date_str} Daily Econ (EN)", en_text)
        send_push(f"{date_str} Daily Econ (KO-from-EN)", ko_text)

    # 국내 기사: 한국어 그대로
    kr_items = get_entries(FEEDS_KR, MAX_PER_FEED_KR, TOTAL_MAX_KR)
    if kr_items:
        kr_text = build_text(kr_items, translate=False)
        send_push(f"{date_str} Daily Econ (KR-국내)", kr_text)

if __name__ == "__main__":
    main()
