#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Локальная выгрузка CSV по списку номеров.

Использование:
    python make_csv.py numbers.txt out.csv
    python make_csv.py            # читает numbers.txt, пишет unitrade.csv
"""

import sys
from pathlib import Path

import report
from trackers import TZ_OFFSET, build


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("numbers.txt")
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("unitrade.csv")
    if not src.exists():
        print("Нет файла со списком номеров:", src)
        return
    nums = [ln.strip() for ln in src.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    if not nums:
        print("Список номеров пуст:", src)
        return
    api = build(["unitrade"])[0]
    items = api.fetch_items(nums)
    csv_text = report.build_csv(nums, items, offset=TZ_OFFSET)
    try:
        dst.write_bytes(csv_text.encode("utf-8"))  # без перевода строк (иначе \r\r\n)
    except PermissionError:
        print("Не удалось записать %s: файл открыт в другой программе (обычно Excel)." % dst)
        print("Закройте его и запустите снова.")
        return
    found = sum(1 for n in nums if items.get(n))
    print("Сохранено: %s | найдено %d из %d" % (dst, found, len(nums)))


if __name__ == "__main__":
    main()
