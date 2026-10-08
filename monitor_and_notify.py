"""演唱會小祕書：抓新聞、算倒數、發 LINE。

只用 Python 內建套件，runner 上不用 pip install。

用法：
    python3 monitor_and_notify.py fetch    # 抓新聞＋算倒數，輸出 message
    python3 monitor_and_notify.py deploy   # 把 message 廣播到 LINE
    python3 monitor_and_notify.py alert    # 前面失敗時發警示

設定都從環境變數讀：ARTIST、LINE_NAME、TODAY、SCENARIO、NOTIFY、MESSAGE、
LINE_CHANNEL_ACCESS_TOKEN、RUN_URL。
"""

import datetime
import email.utils
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from pathlib import Path

TAIPEI = datetime.timezone(datetime.timedelta(hours=8))
CONCERTS_DIR = Path(__file__).parent / "concerts"
NEWS_KEYWORDS = ("演唱會", "售票", "開賣", "門票", "巡演")
NEWS_DAYS = 7
NEWS_LIMIT = 3
# 第 3 關「資料來源失敗」用的網址，.invalid 網域保證連不上
BROKEN_FEED_URL = "https://news.invalid/rss"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def build_feed_url(artist):
    query = urllib.parse.quote(f"{artist} 演唱會")
    return f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


def parse_feed(xml_text):
    """RSS 轉成 [{title, link, published}]。"""
    items = []
    for item in ElementTree.fromstring(xml_text).iter("item"):
        published_text = item.findtext("pubDate")
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": email.utils.parsedate_to_datetime(published_text) if published_text else None,
        })
    return items


def filter_news(items, now, days=NEWS_DAYS, limit=NEWS_LIMIT):
    """留下最近幾天、標題有演唱會相關字眼的新聞，新的在前。"""
    since = now - datetime.timedelta(days=days)
    matched = [
        item for item in items
        if item["published"] and since <= item["published"] <= now
        and any(keyword in item["title"] for keyword in NEWS_KEYWORDS)
    ]
    matched.sort(key=lambda item: item["published"], reverse=True)
    return matched[:limit]


def fetch_news(artist, scenario, now):
    url = BROKEN_FEED_URL if scenario == "資料來源失敗" else build_feed_url(artist)
    request = urllib.request.Request(url, headers={"User-Agent": "cloud-reminder-workshop"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            xml_text = response.read().decode("utf-8")
    except OSError as error:
        raise RuntimeError(f"資料來源連不上：{url}（{error}）") from error
    return filter_news(parse_feed(xml_text), now)


def load_concerts(directory=CONCERTS_DIR):
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


def find_concert(artist, concerts):
    wanted = artist.strip().casefold()
    for concert in concerts:
        if concert["artist"].casefold() == wanted:
            return concert
    for concert in concerts:
        if wanted and wanted in concert["artist"].casefold():
            return concert
    return None


def parse_date(text):
    return datetime.date.fromisoformat(text[:10])


def build_reminders(concert, today):
    """依「今天」算出開賣、演出提醒，回傳要顯示的句子。"""
    if concert is None:
        return ["目前沒有登記這位演唱者的台灣場次。"]

    reminders = []
    sale_at = concert.get("sale_at")
    if sale_at:
        days_to_sale = (parse_date(sale_at) - today).days
        platform = concert.get("platform") or "售票平台"
        if days_to_sale == 1:
            reminders.append(f"🎫 明天 {sale_at[11:]} 在{platform}開賣，先設好鬧鐘、登入帳號。")
        elif days_to_sale == 0:
            reminders.append(f"🎫 今天 {sale_at[11:]} 在{platform}開賣！")

    upcoming = [show for show in concert["shows"] if parse_date(show) >= today]
    if not upcoming:
        reminders.append("演出已經結束了。")
        return reminders
    next_show = upcoming[0]
    days_to_show = (parse_date(next_show) - today).days
    if days_to_show == 0:
        reminders.append(f"🎤 今天（{next_show}）在{concert['venue']}演出！")
    elif days_to_show == 1:
        reminders.append(f"🎤 明天（{next_show}）在{concert['venue']}演出，記得帶票和證件。")
    else:
        reminders.append(f"距離演出還有 {days_to_show} 天（{next_show}，{concert['venue']}）。")
    return reminders


def build_message(line_name, artist, reminders, news):
    lines = [f"🎤 {line_name or '匿名'} 訂閱的 {artist}", *reminders]
    if news:
        lines.append("")
        lines.append("📰 最新消息")
        lines.extend(f"{index}. {item['title']}" for index, item in enumerate(news, start=1))
    return "\n".join(lines)


def broadcast(token, text):
    body = json.dumps({"messages": [{"type": "text", "text": text}]}).encode("utf-8")
    request = urllib.request.Request(
        LINE_BROADCAST_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"LINE 回應 {error.code}：{error.read().decode('utf-8', 'replace')}") from error


def write_output(name, value):
    """把結果交給下一個 job。GitHub Actions 寫 GITHUB_OUTPUT，Azure Pipelines 用 ##vso。"""
    encoded = json.dumps(value, ensure_ascii=False)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"{name}={encoded}\n")
    if os.environ.get("TF_BUILD"):
        print(f"##vso[task.setvariable variable={name};isOutput=true]{encoded}")


def write_summary(markdown):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown + "\n")
    else:
        print(markdown)


def resolve_today(text):
    if not text.strip():
        return datetime.datetime.now(TAIPEI).date()
    try:
        return datetime.date.fromisoformat(text.strip())
    except ValueError as error:
        raise RuntimeError(f"「假設今天是」格式不對：{text}（要寫成 YYYY-MM-DD）") from error


def command_fetch():
    artist = os.environ["ARTIST"].strip()
    line_name = os.environ.get("LINE_NAME", "").strip()
    scenario = os.environ.get("SCENARIO", "正常")
    today = resolve_today(os.environ.get("TODAY", ""))

    concert = find_concert(artist, load_concerts())
    if concert:
        artist = concert["artist"]
    news = fetch_news(artist, scenario, datetime.datetime.now(TAIPEI))
    reminders = build_reminders(concert, today)
    message = build_message(line_name, artist, reminders, news)
    write_output("message", message)

    news_lines = [f"- [{item['title']}]({item['link']})" for item in news] or ["- 最近 7 天沒有相關新聞"]
    write_summary("\n".join([
        f"## 🎤 {line_name or '匿名'} 訂閱的 {artist}",
        f"- 今天（台北）：{today}",
        *[f"- {reminder}" for reminder in reminders],
        "",
        "### 📰 最新消息",
        *news_lines,
        "",
        f"### 📱 要發的 LINE 訊息\n```\n{message}\n```",
    ]))


def command_deploy():
    message = json.loads(os.environ["MESSAGE"])
    broadcast(os.environ["LINE_CHANNEL_ACCESS_TOKEN"], message)
    write_summary("## ✅ 已發送 LINE 通知")


def command_alert():
    artist = os.environ.get("ARTIST", "")
    line_name = os.environ.get("LINE_NAME", "").strip() or "匿名"
    text = f"⚠️ {line_name} 訂閱 {artist} 的流程失敗了，這次不發通知。\n查看原因：{os.environ.get('RUN_URL', '')}"
    if os.environ.get("NOTIFY", "").lower() == "true":
        broadcast(os.environ["LINE_CHANNEL_ACCESS_TOKEN"], text)
        write_summary("## ⚠️ 已發送 LINE 警示")
    else:
        write_summary("## ⚠️ 流程失敗（沒勾選收通知，不發 LINE）")
    write_summary(text)


COMMANDS = {"fetch": command_fetch, "deploy": command_deploy, "alert": command_alert}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"用法：python3 {Path(__file__).name} {{{'|'.join(COMMANDS)}}}")
    try:
        COMMANDS[sys.argv[1]]()
    except RuntimeError as error:
        print(f"::error::{error}")
        sys.exit(1)
