# -*- coding: utf-8 -*-
import os, textwrap, datetime, requests
import feedparser

# -------- 설정 --------
FEEDS = [
    "https://www.ft.com/rss/home",                                  # Financial Times
    "https://www.economist.com/finance-and-economics/rss.xml",      # The Economist - Finance & economics
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",                  # Wall Street Journal (월드 섹션)
    "https://feeds.reuters.com/reuters/businessNews",               # Reuters Business
]
MAX_PER_FEED = int(os.environ.get("MAX_PER_FEED", "3"))    # 피드당 기사 최대 개수
TOTAL_MAX = int(os.environ.get("TOTAL_MAX", "10"))         # 전체 최대 기사 수

# ntfy (폰 푸시)
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")   # 예: jusun-econ-daily-9am-7b3f9f

# -------- 번역 (자동) --------
# deep_translator 우선, 실패 시 googletrans 폴백
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
            return text  # 번역 실패하면 원문 그대로

# -------- 유틸 --------
def strip_html(html_text: str) -> str:
    import re
    return re.sub("<[^<]+?>", "", html_text or "").strip()

def safe_get(d, key, default=""):
    return d.get(key, default) if isinstance(d, dict) else default

def fetch_news():
    items = []
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:MAX_PER_FEED]:
                title = safe_get(e, "title", "(no title)")
                link = safe_get(e, "link", "")
                summary = safe_get(e, "summary", "") or safe_get(e, "description", "")
                if summary:
                    summary = textwrap.shorten(strip_html(summary), width=280, placeholder="…")
                items.append({"title": title, "link": link, "summary": summary})
        except Exception as ex:
            print("feed error:", url, repr(ex))
    return items[:TOTAL_MAX]

def build_texts(items):
    # 1) 원문(EN)
    en_lines = []
    for i, it in enumerate(items, 1):
        en_lines.append(f"{i}. {it['title']}")
        if it["summary"]:
            en_lines.append(f" - {it['summary']}")
        if it["link"]:
            en_lines.append(it["link"])
        en_lines.append("")  # 빈 줄
    en_text = "\n".join(en_lines).strip()

    # 2) 한국어(번역)
    ko_lines = []
    for i, it in enumerate(items, 1):
        title_ko = translate_ko(it["title"])
        sum_ko = translate_ko(it["summary"]) if it["summary"] else ""
        ko_lines.append(f"{i}. {title_ko}")
        if sum_ko:
            ko_lines.append(f" - {sum_ko}")
        if it["link"]:
            ko_lines.append(it["link"])
        ko_lines.append("")
    ko_text = "\n".join(ko_lines).strip()
    return en_text, ko_text

def send_push(title: str, body: str):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set; skip push")
        return
    # 너무 길면 나눠서 보냄(푸시 노출 길이 제한 대비)
    chunks = chunk_text(body, 1500)
    for idx, ch in enumerate(chunks, 1):
        t = title if len(chunks) == 1 else f"{title} ({idx}/{len(chunks)})"
        try:
            requests.post(
                f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}",
                data=ch.encode("utf-8"),
                headers={"Title": t},
                timeout=20
            )
        except Exception as e:
            print("ntfy push failed:", repr(e))

def chunk_text(s: str, max_len: int):
    # 줄 단위로 잘라 최대 길이 넘지 않게 묶어줌
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

def main():
    items = fetch_news()
    if not items:
        print("no news today"); return

    en_text, ko_text = build_texts(items)

    # 제목: YYYY-MM-DD Daily Econ (KST)
    kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    date_str = kst.strftime("%Y-%m-%d")

    send_push(f"{date_str} Daily Econ (EN)", en_text)
    send_push(f"{date_str} Daily Econ (KO)", ko_text)

if __name__ == "__main__":
    main()
