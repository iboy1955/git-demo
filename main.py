import os
import sys
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import requests

API_URL = "https://aihot.virxact.com/api/public/items?mode=selected"
MAX_ITEMS = 15
SUMMARY_MAX_LEN = 200
FALLBACK_COUNT = 10

SHANGHAI = ZoneInfo("Asia/Shanghai")


def fetch_aihot():
    res = requests.get(
        API_URL,
        timeout=15,
        headers={"User-Agent": "AIHOT-Daily-Mailer/1.0"},
    )
    try:
        res.raise_for_status()
    except requests.HTTPError:
        print(f"ERROR: API request failed with status {res.status_code}")
        sys.exit(1)
    return res.json()


def _parse_published_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def filter_items(items):
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=24)

    recent = []
    for item in items:
        published = _parse_published_at(item.get("publishedAt"))
        if published and published >= cutoff:
            recent.append(item)

    recent.sort(
        key=lambda x: _parse_published_at(x.get("publishedAt")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    if recent:
        return recent, False

    fallback = items[:FALLBACK_COUNT]
    return fallback, True


def _truncate(text, max_len):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _item_link(item):
    return item.get("permalink") or item.get("url") or ""


def build_email(items, is_fallback):
    display_items = items[:MAX_ITEMS]
    today = datetime.now(SHANGHAI).strftime("%Y-%m-%d")
    count = len(display_items)

    if is_fallback:
        header_note = "近 24 小时无新增，以下为最新精选"
        period = "统计时段：最新精选（兜底）"
    else:
        header_note = None
        period = "统计时段：过去 24 小时"

    lines = [
        f"AIHOT 每日简报 ({today})",
        "",
    ]
    if header_note:
        lines.append(header_note)
        lines.append("")
    lines.extend([
        f"共 {count} 条 | {period}",
        "",
    ])

    if not display_items:
        lines.append("暂无数据")
    else:
        for i, item in enumerate(display_items, 1):
            title = item.get("title") or "无标题"
            source = item.get("source") or "未知来源"
            summary = _truncate(item.get("summary") or "", SUMMARY_MAX_LEN)
            link = _item_link(item)

            lines.append("─" * 24)
            lines.append(f"{i}. {title}")
            lines.append(f"   来源：{source}")
            if summary:
                lines.append(f"   摘要：{summary}")
            if link:
                lines.append(f"   链接：{link}")

    lines.extend([
        "",
        "─" * 24,
        "自动生成：AIHOT Daily Bot",
    ])

    subject = f"AIHOT 每日简报 {today}（{count}条）"
    return subject, "\n".join(lines)


def _require_env(name):
    value = os.getenv(name)
    if not value:
        print(f"ERROR: missing environment variable {name}")
        sys.exit(1)
    return value


def send_email(subject, content):
    sender = _require_env("EMAIL_SENDER")
    password = _require_env("EMAIL_PASSWORD")
    receiver = _require_env("EMAIL_RECEIVER")

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver

    smtp = None
    try:
        smtp = smtplib.SMTP_SSL("smtp.qq.com", 465)
        smtp.login(sender, password)
        smtp.sendmail(sender, receiver, msg.as_string())
    except smtplib.SMTPException as e:
        print(f"ERROR: failed to send email: {e}")
        sys.exit(1)
    finally:
        if smtp:
            smtp.quit()


def main():
    data = fetch_aihot()
    items, is_fallback = filter_items(data.get("items", []))
    subject, content = build_email(items, is_fallback)
    send_email(subject, content)

    receiver = os.getenv("EMAIL_RECEIVER", "")
    sent_count = min(len(items), MAX_ITEMS)
    print(f"OK: sent {sent_count} items to {receiver}")


if __name__ == "__main__":
    main()
