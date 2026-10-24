#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Интерактивный Telegram-бот: принимает список трек-номеров, отвечает статусами.

Режимы:
  python bot.py            # long polling (постоянный хостинг / локально)
  python bot.py --once     # обработать накопившиеся сообщения и выйти (для cron)

Переменные окружения:
  BOT_TOKEN (или TELEGRAM_BOT_TOKEN) — токен бота от @BotFather
  TRACKERS                           — сайты через запятую (иначе из trackers.txt)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

import importers
import report
from trackers import TZ_OFFSET
from trackers import build as build_trackers

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent
TRACKERS_FILE = ROOT / "trackers.txt"
STATE_FILE = ROOT / "bot_state.json"
API = "https://api.telegram.org/bot%s/%s"
TIMEOUT = 30
MAX_MSG = 4000
FAILED = {"n": 0}  # счётчик неудачных отправок (чтобы запуск в CI краснел)

HELP = (
    "🤖 UNI Monitor\n\n"
    "Пришлите список трек-номеров — верну CSV с прохождением 10 этапов.\n\n"
    "Как отправить:\n"
    "• текстом — по одному в строке / через запятую;\n"
    "• или файлом: .txt, .csv, .xlsx (номера в любых ячейках).\n\n"
    "Пример:\n"
    "WBCNRUDPCCG2600V4G\n"
    "83157823-0374-1\n\n"
    "Команды:\n"
    "/sites — активные сайты\n"
    "/id — узнать свой chat id\n"
    "/help — эта справка"
)


def load_tracker_names():
    """Имена активных сайтов: из переменной TRACKERS или из trackers.txt."""
    env = os.environ.get("TRACKERS", "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    names = []
    if TRACKERS_FILE.exists():
        for line in TRACKERS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return names or ["track24"]


def parse_numbers(text):
    """Вытаскивает из текста трек-номера (>=6 символов, содержат цифру)."""
    out = []
    for tok in re.split(r"[\s,;]+", text or ""):
        tok = tok.strip().strip(".:;!?()[]")
        if (len(tok) >= 6 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-]{5,}", tok)
                and re.search(r"\d", tok)):
            if tok not in out:
                out.append(tok)
    return out


def process(text, trackers):
    """Прогоняет найденные номера по активным сайтам, возвращает текст ответа."""
    nums = parse_numbers(text)
    if not nums:
        return ("Не вижу трек-номеров 🤔\n\n"
                "Пришлите список — по одному в строке или через запятую.\n"
                "Пример:\nWBCNRUDPCCG2600V4G\n83157823-0374-1")
    results = []
    for t in trackers:
        try:
            res = t.track_many(nums)
        except Exception as e:  # noqa: BLE001
            res = {n: "ошибка (%s)" % type(e).__name__ for n in nums}
        results.append((t, res))
    lines = ["📦 Найдено номеров: %d" % len(nums),
             "Сайты: " + ", ".join(t.title for t in trackers), ""]
    for n in nums:
        lines.append("📮 %s" % n)
        for t, res in results:
            st = res.get(n)
            lines.append("   • %s: %s" % (t.title, st if st else "нет данных"))
        lines.append("")
    return "\n".join(lines).strip()


def tg_call(token, method, **params):
    return requests.post(API % (token, method), data=params,
                         timeout=TIMEOUT + 15).json()


def send(token, chat_id, text):
    """Отправляет текст (при необходимости — несколькими сообщениями)."""
    text = text or ""
    for i in range(0, len(text), MAX_MSG):
        r = tg_call(token, "sendMessage", chat_id=chat_id,
                    text=text[i:i + MAX_MSG], disable_web_page_preview="true")
        if not r.get("ok"):
            FAILED["n"] += 1
            print("sendMessage error:", r)


def allowed_chat(chat_id):
    """Белый список чатов (ALLOWED_CHAT_IDS через запятую). Пусто = разрешено всем."""
    raw = os.environ.get("ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return True
    allowed = [x.strip() for x in raw.split(",") if x.strip()]
    return str(chat_id) in allowed


def send_document(token, chat_id, filename, content, caption=""):
    """Отправляет файл (например, CSV) в чат."""
    try:
        r = requests.post(API % (token, "sendDocument"),
                          data={"chat_id": chat_id, "caption": caption[:900]},
                          files={"document": (filename, content, "text/csv")},
                          timeout=TIMEOUT + 30)
        res = r.json()
        print("sendDocument:", "OK" if res.get("ok") else res)
        if not res.get("ok"):
            FAILED["n"] += 1
        return res
    except Exception as e:  # noqa: BLE001
        print("sendDocument error:", e)
        return {"ok": False}


def download_file(token, file_id):
    """Скачивает файл из Telegram, возвращает bytes."""
    info = requests.get(API % (token, "getFile"),
                        params={"file_id": file_id}, timeout=TIMEOUT).json()
    if not info.get("ok"):
        raise RuntimeError("getFile: %s" % info)
    path = info["result"]["file_path"]
    r = requests.get("https://api.telegram.org/file/bot%s/%s" % (token, path),
                     timeout=TIMEOUT + 60)
    r.raise_for_status()
    return r.content


def build_and_send_csv(token, chat_id, nums, trackers):
    """Строит CSV по номерам и отправляет файлом."""
    api = next((t for t in trackers if getattr(t, "name", "") == "unitrade"), None)
    if api is None:
        send(token, chat_id, process("\n".join(nums), trackers))
        return
    send(token, chat_id, "Обрабатываю %d номеров…" % len(nums))
    try:
        items = api.fetch_items(nums)
        data = report.build_csv(nums, items, offset=TZ_OFFSET)
        fname = "unitrade_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M")
        found = sum(1 for n in nums if items.get(n))
        send_document(token, chat_id, fname, data.encode("utf-8"),
                      caption="Готово: найдено %d из %d" % (found, len(nums)))
    except Exception as e:  # noqa: BLE001
        send(token, chat_id, "Ошибка при формировании CSV: %s" % type(e).__name__)


def handle_document(token, chat_id, doc, trackers):
    """Обрабатывает присланный файл со списком номеров."""
    name = doc.get("file_name") or "file"
    size = doc.get("file_size") or 0
    if size > 20 * 1024 * 1024:
        send(token, chat_id, "Файл слишком большой (максимум 20 МБ).")
        return
    try:
        content = download_file(token, doc["file_id"])
    except Exception as e:  # noqa: BLE001
        send(token, chat_id, "Не удалось скачать файл: %s" % type(e).__name__)
        return
    try:
        nums = importers.numbers_from_file(name, content)
    except importers.Unsupported as e:
        send(token, chat_id, str(e))
        return
    except Exception as e:  # noqa: BLE001
        send(token, chat_id, "Не удалось прочитать файл: %s" % type(e).__name__)
        return
    if not nums:
        send(token, chat_id, "В файле «%s» не нашёл трек-номеров." % name)
        return
    build_and_send_csv(token, chat_id, nums, trackers)


def handle_update(token, upd, trackers):
    """Обрабатывает одно сообщение пользователя."""
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    if not allowed_chat(chat_id):
        print("Сообщение из неразрешённого чата %s — пропущено" % chat_id)
        return
    doc = msg.get("document")
    if doc:
        handle_document(token, chat_id, doc, trackers)
        return

    text = (msg.get("text") or "").strip()
    low = text.lower()
    if low.startswith("/id"):
        send(token, chat_id, "Ваш chat id: %s" % chat_id)
    elif low.startswith("/sites"):
        send(token, chat_id, "Активные сайты: " + ", ".join(t.title for t in trackers))
    elif low.startswith("/start") or low.startswith("/help") or not text:
        send(token, chat_id, HELP)
    else:
        nums = parse_numbers(text)
        if not nums:
            send(token, chat_id, HELP)
            return
        build_and_send_csv(token, chat_id, nums, trackers)


def load_offset():
    """Позиция обработки сообщений (чтобы не переобрабатывать старые)."""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("offset")
    except Exception:  # noqa: BLE001
        return None


def save_offset(offset):
    try:
        STATE_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print("save_offset error:", e)


def read_token_file():
    """Токен можно положить в token.txt рядом с bot.py — удобно для локального запуска."""
    p = ROOT / "token.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="обработать накопившиеся сообщения и выйти (для cron)")
    args = ap.parse_args()

    token = (os.environ.get("BOT_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN")
             or read_token_file())
    if not token:
        print("Не задан токен: положите его в файл token.txt (рядом с bot.py) "
              "или задайте переменную BOT_TOKEN")
        sys.exit(1)

    # Проверяем токен сразу — иначе ошибка «спрячется» в зелёном запуске
    try:
        me = requests.get(API % (token, "getMe"), timeout=TIMEOUT).json()
    except Exception as e:  # noqa: BLE001
        print("Не удалось связаться с Telegram:", e)
        sys.exit(4)
    if not me.get("ok"):
        print("Telegram не принял токен:", me)
        sys.exit(4)
    info = me.get("result") or {}
    print("Бот: @%s (id %s)" % (info.get("username"), info.get("id")))

    trackers = build_trackers(load_tracker_names())
    if not trackers:
        print("Нет активных сайтов — проверьте trackers.txt")
        sys.exit(1)
    print("Активные сайты:", ", ".join(t.title for t in trackers))

    offset = load_offset()
    while True:
        params = {"timeout": 0 if args.once else 25}
        if offset is not None:
            params["offset"] = offset
        try:
            data = requests.get(API % (token, "getUpdates"), params=params,
                                timeout=TIMEOUT + 15).json()
        except Exception as e:  # noqa: BLE001
            print("getUpdates error:", e)
            if args.once:
                sys.exit(5)
            time.sleep(5)
            continue
        if not data.get("ok"):
            print("Telegram error:", data)
            if args.once:
                sys.exit(5)
            time.sleep(5)
            continue
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            try:
                handle_update(token, upd, trackers)
            except Exception as e:  # noqa: BLE001
                print("handle error:", e)
        if offset is not None:
            save_offset(offset)
        if args.once:
            break

    if FAILED["n"]:
        print("Ошибок отправки в Telegram: %d" % FAILED["n"])
        sys.exit(6)


if __name__ == "__main__":
    main()
