#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blogfa -> Markdown exporter for delkash.blogfa.com
Only the Python standard library is needed (no pip install).

Usage (Git Bash / CMD, inside an empty folder):
    python blogfa_export.py --test post.html          # parse one local file only
    python blogfa_export.py --limit 5                 # download the first 5 posts
    python blogfa_export.py                           # download everything (310 posts)

Outputs (next to the script):
    export/raw/<id>.html      the untouched page as downloaded (your safety copy)
    export/posts/<id>.md      front matter + the post body as HTML
    export/index.csv          one row per post (id, title, date, tags, audio, ...)
    export/report.txt         counts + list of posts that failed or looked suspicious
The script is resumable: posts whose raw file already exists are not downloaded again.
"""
import argparse, csv, html, json, re, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://delkash.blogfa.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
OUT = Path("export")

# ---------- Persian date helpers ----------
MONTHS = {"فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "شهریور": 6,
          "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12}
ORD_ONES = ["", "یکم", "دوم", "سوم", "چهارم", "پنجم", "ششم", "هفتم", "هشتم", "نهم"]
DAY_WORDS = {"اول": 1, "دهم": 10, "یازدهم": 11, "دوازدهم": 12, "سیزدهم": 13, "چهاردهم": 14,
             "پانزدهم": 15, "شانزدهم": 16, "هفدهم": 17, "هجدهم": 18, "نوزدهم": 19,
             "بیستم": 20, "سی‌ام": 30, "سی ام": 30, "سی‌ام": 30}
for i, w in enumerate(ORD_ONES):
    if i:
        DAY_WORDS[w] = i
        DAY_WORDS["بیست و " + w] = 20 + i
        DAY_WORDS["سی و " + w] = 30 + i
DAY_WORDS["سی و یکم"] = 31
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30 + 186)
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 29 if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0 else 28,
             31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def parse_fa_date(text):
    """'هفتم خرداد ۱۳۹۹ ساعت 13:6' -> ('1399-03-07', '2020-05-27T13:06:00', raw) or (None, None, raw)"""
    raw = " ".join(text.split())
    t = raw.translate(FA_DIGITS)
    m = re.search(r"(.+?)\s+(" + "|".join(MONTHS) + r")\s+(\d{4})(?:\s+ساعت\s+(\d+):(\d+))?", t)
    if not m:
        return None, None, raw
    day_s, mon, year, hh, mm = m.groups()
    day_s = day_s.strip()
    day = int(day_s) if day_s.isdigit() else DAY_WORDS.get(day_s)
    if not day:
        return None, None, raw
    jy, jm = int(year), MONTHS[mon]
    gy, gm, gd = jalali_to_gregorian(jy, jm, day)
    jal = f"{jy:04d}-{jm:02d}-{day:02d}"
    iso = f"{gy:04d}-{gm:02d}-{gd:02d}T{int(hh or 0):02d}:{int(mm or 0):02d}:00"
    return jal, iso, raw


# ---------- page parsing ----------
def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_post(page, post_id):
    d = {"id": post_id, "problems": []}
    m = re.search(r'<article class="post">.*?<h2><a href="/post/(\d+)">(.*?)</a></h2>', page, re.S)
    if not m:
        d["problems"].append("no title block")
        return d
    d["page_id"] = int(m.group(1))
    if d["page_id"] != post_id:
        d["problems"].append(f"id mismatch (page says {d['page_id']})")
    d["title"] = strip_tags(m.group(2))
    m = re.search(r'<div class="postcontent">(.*?)<div class="clear"></div>\s*</div>', page, re.S)
    if m:
        d["body_html"] = m.group(1).strip()
    else:
        d["body_html"] = ""
        d["problems"].append("no postcontent")
    tags = re.search(r'<div class="posttags">(.*?)</div>', page, re.S)
    d["tags"] = [strip_tags(x) for x in re.findall(r"<a [^>]*>(.*?)</a>", tags.group(1), re.S)] if tags else []
    info = re.search(r'<div class="postinfo">(.*?)<div class="clear">', page, re.S)
    infotxt = strip_tags(info.group(1)) if info else ""
    dm = re.search(r"نوشته شده در\s*(.*?)\s*توسط\s*(.*?)(?:\||$)", " ".join(infotxt.split()))
    d["jalali_date"], d["date"], d["date_raw"] = (None, None, "")
    d["author"] = ""
    if dm:
        d["jalali_date"], d["date"], d["date_raw"] = parse_fa_date(dm.group(1))
        d["author"] = dm.group(2).strip()
    if not d["date"]:
        d["problems"].append("date not parsed")
    body = d["body_html"]
    d["audio_links"] = sorted(set(re.findall(r'href="(https?://[^"]*(?:\.mp3|\.m4a|\.wav)[^"]*)"', body, re.I)))
    d["images"] = [u for u in dict.fromkeys(re.findall(r'<img[^>]*src="([^"]+)"', body)) if "icon_download" not in u]
    d["other_links"] = [u for u in dict.fromkeys(re.findall(r'href="(https?://[^"]+)"', body)) if u not in d["audio_links"]]
    d["text_chars"] = len(strip_tags(body))
    if d["text_chars"] < 20:
        d["problems"].append("very short body")
    if re.search(r"ادامه\s*(?:ی)?\s*(?:نوشته|مطلب)", body):
        d["problems"].append("body mentions 'continue reading' - may be truncated")
    return d


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def to_markdown(d):
    fm = ["---",
          f"title: {yaml_str(d['title'])}",
          f"date: {d['date']}" if d.get("date") else "date: null",
          f"blogfa_id: {d['id']}",
          f"blogfa_url: {yaml_str(BASE + '/post/' + str(d['id']))}",
          f"jalali_date: {yaml_str(d.get('jalali_date') or '')}",
          f"jalali_date_raw: {yaml_str(d.get('date_raw') or '')}",
          f"author: {yaml_str(d.get('author') or '')}",
          "tags: " + json.dumps(d["tags"], ensure_ascii=False),
          "audio_links: " + json.dumps(d["audio_links"], ensure_ascii=False),
          "images: " + json.dumps(d["images"], ensure_ascii=False),
          "draft: true",
          "---", ""]
    return "\n".join(fm) + d["body_html"] + "\n"


# ---------- network ----------
def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fa,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", help="parse one local HTML file and print the result")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    a = ap.parse_args()

    if a.test:
        page = Path(a.test).read_text(encoding="utf-8", errors="replace")
        pid = int(re.search(r'<h2><a href="/post/(\d+)"', page).group(1))
        d = parse_post(page, pid)
        (OUT / "posts").mkdir(parents=True, exist_ok=True)
        (OUT / "posts" / f"{pid}.md").write_text(to_markdown(d), encoding="utf-8")
        show = {k: v for k, v in d.items() if k != "body_html"}
        print(json.dumps(show, ensure_ascii=False, indent=1))
        print("written:", OUT / "posts" / f"{pid}.md")
        return

    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    (OUT / "posts").mkdir(parents=True, exist_ok=True)
    sm = fetch(BASE + "/sitemap.xml")
    ids = sorted({int(x) for x in re.findall(r"/post/(\d+)</loc>", sm)}, reverse=True)
    if a.limit:
        ids = ids[: a.limit]
    print(f"{len(ids)} posts to process")
    rows, bad = [], []
    for n, pid in enumerate(ids, 1):
        raw = OUT / "raw" / f"{pid}.html"
        try:
            if raw.exists():
                page = raw.read_text(encoding="utf-8")
            else:
                page = fetch(f"{BASE}/post/{pid}")
                raw.write_text(page, encoding="utf-8")
                time.sleep(a.delay)
            d = parse_post(page, pid)
        except Exception as e:
            bad.append((pid, str(e)))
            print(f"[{n}/{len(ids)}] {pid} FAILED: {e}")
            continue
        if d.get("title"):
            (OUT / "posts" / f"{pid}.md").write_text(to_markdown(d), encoding="utf-8")
        if d["problems"]:
            bad.append((pid, "; ".join(d["problems"])))
        rows.append(d)
        print(f"[{n}/{len(ids)}] {pid} {d.get('title','?')[:50]} {'!' if d['problems'] else ''}")

    with open(OUT / "index.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "jalali_date", "title", "tags", "audio_links", "images", "text_chars", "problems"])
        for d in rows:
            w.writerow([d["id"], d.get("date"), d.get("jalali_date"), d.get("title"), "|".join(d.get("tags", [])),
                        "|".join(d.get("audio_links", [])), len(d.get("images", [])), d.get("text_chars"),
                        "; ".join(d["problems"])])
    ok = [d for d in rows if not d["problems"]]
    rep = [f"posts requested : {len(ids)}", f"parsed          : {len(rows)}",
           f"clean           : {len(ok)}", f"with problems   : {len(bad)}",
           f"with audio links: {sum(1 for d in rows if d.get('audio_links'))}",
           f"with tags       : {sum(1 for d in rows if d.get('tags'))}", ""]
    rep += [f"{pid}: {why}" for pid, why in bad]
    (OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep[:6]))
    print("details in export/report.txt")


if __name__ == "__main__":
    main()
