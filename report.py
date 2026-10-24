# -*- coding: utf-8 -*-
"""CSV-отчёт по посылкам: 10 этапов прохождения (как на портале).

Формат: 1 колонка «Номер» + 10 колонок с датами прохождения этапов.
Разделитель — ';', кодировка UTF-8 с BOM (открывается в Excel).
"""

import csv
import io
from datetime import datetime, timedelta, timezone

# (название этапа, типы событий API; "created" = время создания отправления)
STAGES = [
    ("Ожидает отправки на склад", "created"),
    ("Поступил на склад первой мили", [101]),
    ("Отправлен на таможню: экспорт", [150]),
    ("Поступил на таможню: экспорт", [200]),
    ("Прошёл таможню: экспорт", [250]),
    ("Поступил на таможню: импорт", [301]),
    ("Прошёл таможню: импорт", []),
    ("Поступил на склад последней мили", [401]),
    ("На пути в город назначения", []),
    ("Доступен в точке выдачи", [404]),
]

REASONS = {
    2: "не забрали в пункте выдачи",
    6: "отказ покупателя",
}


def _fmt(iso, offset):
    try:
        dt = datetime.strptime((iso or "")[:19], "%Y-%m-%dT%H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=offset)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def build_csv(numbers, items, offset=10):
    """Возвращает текст CSV (с BOM). items: dict номер -> сырой объект API."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Номер"] + [s[0] for s in STAGES])

    for n in numbers:
        item = items.get(n)
        if not item:
            w.writerow([n] + [""] * len(STAGES))
            continue

        evs = sorted(item.get("trackEvents") or [],
                     key=lambda e: e.get("moment") or "")
        first_by_type = {}
        for e in evs:
            first_by_type.setdefault(e.get("type"), e)

        cells = []
        for _, types in STAGES:
            if types == "created":
                cells.append(_fmt(item.get("createdAt"), offset))
                continue
            val = ""
            for t in types:
                if t in first_by_type:
                    val = _fmt(first_by_type[t].get("moment"), offset)
                    break
            cells.append(val)

        cancel = next((e for e in evs if e.get("type") == 5000), None)
        note = ""
        if cancel is not None:
            note = "отменён: %s" % REASONS.get(
                cancel.get("cancellationReasonType"),
                "причина %s" % cancel.get("cancellationReasonType"))
        elif 10000 in first_by_type:
            note = "доставлен %s" % _fmt(first_by_type[10000].get("moment"), offset)

        last_idx = max([i for i, c in enumerate(cells) if c], default=-1)
        if note and last_idx >= 0:
            cells[last_idx] = "%s (%s)" % (cells[last_idx], note)

        w.writerow([n] + cells)

    return "\ufeff" + buf.getvalue()
