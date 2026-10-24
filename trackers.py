# -*- coding: utf-8 -*-
"""Трекеры (сайты) для прогона посылок в боте.

Каждый трекер — класс с полями/методами:
    name          : str          # короткое имя (используется в trackers.txt)
    title         : str          # человекочитаемое название
    track(number) -> str | None  # строка статуса или None, если данных нет

Чтобы добавить новый сайт: реализуйте класс по образцу и добавьте его в TRACKERS.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 30


class Track24:
    """track24.ru — запрос по серверному 'trackingKey' (проверено рабочим)."""

    name = "track24"
    title = "track24.ru"

    def __init__(self):
        self.session = None
        self.key = None
        self.ip = None

    def connect(self):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        r = s.get("https://track24.ru/service/unit/tracking/", timeout=TIMEOUT)
        k = re.search(r"var trackingKey = '([0-9a-f]+)'", r.text)
        i = re.search(r'var clientIp = "([0-9.]+)"', r.text)
        self.session = s
        self.key = k.group(1) if k else None
        self.ip = i.group(1) if i else None

    def track(self, number):
        if self.session is None or not self.key:
            try:
                self.connect()
            except Exception:  # noqa: BLE001
                return None
        if not self.key:
            return None
        data = {
            "code": number, "selectedService": "unit", "lng": "ru", "sort": "0",
            "grouped": "0", "type": "cache", "key": self.key, "clientIp": self.ip,
            "uuid": str(uuid.uuid4()), "fingerprint": "",
        }
        try:
            r = self.session.post(
                "https://track24.ru/tracking/?code=%s" % number,
                data=data, timeout=TIMEOUT,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": "https://track24.ru/service/unit/tracking/%s/" % number,
                })
        except Exception:  # noqa: BLE001
            return None
        m = re.search(r'og:description" content="([^"]+)"', r.text)
        if not m:
            return None
        val = m.group(1).strip()
        if "Отслеживание почтовых" in val:  # страница-заглушка = данных нет
            return None
        return val

    def track_many(self, numbers):
        out = {}
        for n in numbers:
            out[n] = self.track(n)
            time.sleep(0.4)
        return out


# ---- UNI (api.unitrade.space) ----

TYPES = {
    50: "заказ создан",
    55: "обработка заказа",
    56: "обработка заказа",
    101: "склад первой мили",
    150: "отправлен на таможню (экспорт)",
    151: "на таможне (экспорт)",
    200: "поступил на таможню (экспорт)",
    201: "таможенное оформление (экспорт)",
    250: "прошёл таможню (экспорт)",
    251: "таможенное оформление (экспорт)",
    300: "в пути",
    301: "поступил на таможню (импорт)",
    305: "ожидает отправки",
    306: "ожидает отправки на склад",
    307: "таможенное оформление (импорт)",
    340: "передан в доставку",
    350: "в пути к получателю",
    401: "склад последней мили",
    404: "доступен в точке выдачи",
    5000: "отменён",
    10000: "доставлен",
}

REASONS = {
    2: "не забрали в пункте выдачи",
    6: "отказ покупателя",
}

# Смещение времени для отображения (портал показывает локальное время).
# По умолчанию +10 (как в браузере пользователя). Меняется через TZ_OFFSET.
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "10"))


class UnitradeApi:
    """Публичный API UNI (Россия, api.unitrade.space). Работает пачкой номеров."""

    name = "unitrade"
    title = "unitrade API"
    BASE = "https://api.unitrade.space/v1/public/track-events"
    CHUNK = 50

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": UA,
            "Origin": "https://unitrade.youtrack.info",
            "Referer": "https://unitrade.youtrack.info/",
        })

    def _fetch(self, chunk):
        last = None
        for attempt in range(3):
            last = self.session.get(self.BASE, timeout=TIMEOUT, params={
                "trackNumbers": "[]",
                "externalNumbers": json.dumps(chunk),
            })
            if last.status_code == 429:  # лимит 1 запрос/сек
                time.sleep(2 + attempt * 2)
                continue
            return last
        return last

    def track(self, number):
        return self.track_many([number]).get(number)

    def fetch_items(self, numbers):
        """Сырые объекты API: dict номер -> item (нужно для CSV)."""
        out = {n: None for n in numbers}
        uniq = list(dict.fromkeys(numbers))
        for i in range(0, len(uniq), self.CHUNK):
            chunk = uniq[i:i + self.CHUNK]
            try:
                r = self._fetch(chunk)
            except Exception:  # noqa: BLE001
                r = None
            if r is not None and r.status_code == 200:
                try:
                    items = r.json()
                except Exception:  # noqa: BLE001
                    items = []
                for it in items:
                    n = it.get("externalNumber") or it.get("trackNumber")
                    if n in out:
                        out[n] = it
            time.sleep(1.1)
        return out

    def track_many(self, numbers):
        items = self.fetch_items(numbers)
        return {n: (self._format(it) if it else None) for n, it in items.items()}

    @staticmethod
    def _moment(iso):
        try:
            dt = datetime.strptime((iso or "")[:19], "%Y-%m-%dT%H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=TZ_OFFSET)
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:  # noqa: BLE001
            return (iso or "")[:16].replace("T", " ")

    @staticmethod
    def _format(item):
        evs = sorted(item.get("trackEvents") or [],
                     key=lambda e: e.get("moment") or "")
        if not evs:
            return None
        cancel = next((e for e in evs if e.get("type") == 5000), None)
        if cancel is None:
            cancel = next((e for e in evs if e.get("cancellationReasonType")), None)
        non_cancel = [e for e in evs if e.get("type") != 5000]
        last = non_cancel[-1] if non_cancel else evs[-1]
        ltype = last.get("type")
        label = TYPES.get(ltype, "этап %s" % ltype)
        date = UnitradeApi._moment(last.get("moment"))
        if cancel is not None:
            reason = REASONS.get(cancel.get("cancellationReasonType"),
                                 "причина %s" % cancel.get("cancellationReasonType"))
            return "ОТМЕНЁН (%s) — %s, %s" % (reason, label, date)
        if ltype == 10000:
            return "ДОСТАВЛЕН — %s" % date
        return "%s, %s" % (label, date)


# Реестр всех реализованных трекеров: name -> класс
TRACKERS = {
    "unitrade": UnitradeApi,
    "track24": Track24,
}


def build(names):
    """Создаёт экземпляры трекеров по списку имён (неизвестные игнорируются)."""
    out = []
    for n in names:
        cls = TRACKERS.get(n)
        if cls:
            out.append(cls())
    return out
