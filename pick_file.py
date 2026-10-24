#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оконный запуск: выбрать файл со списком номеров -> получить CSV.

Двойной клик по run_pick.bat (или: python pick_file.py)
"""

import os
import traceback
from pathlib import Path
from tkinter import Tk, Label, filedialog, messagebox

import importers
import report
from trackers import TZ_OFFSET, build

FILETYPES = [
    ("Excel / CSV / текст", "*.xlsx *.csv *.txt"),
    ("Excel", "*.xlsx"),
    ("CSV", "*.csv"),
    ("Текстовый файл", "*.txt"),
    ("Все файлы", "*.*"),
]


def unique_path(path):
    """Не перезаписываем существующий файл (и не мешаем открытому в Excel)."""
    path = Path(path)
    if not path.exists():
        return path
    for i in range(2, 1000):
        cand = path.with_name("%s (%d)%s" % (path.stem, i, path.suffix))
        if not cand.exists():
            return cand
    return path


def process_file(src, offset=TZ_OFFSET, progress=None):
    """Читает номера из файла, запрашивает API, сохраняет CSV рядом с исходным.

    Возвращает: {"dst": Path, "found": int, "total": int}
    """
    src = Path(src)
    nums = importers.numbers_from_file(src.name, src.read_bytes())
    if not nums:
        raise ValueError("В файле не нашлось ни одного трек-номера.")
    if progress:
        progress("Найдено %d номеров.\nЗапрашиваю статусы…" % len(nums))

    api = build(["unitrade"])[0]
    items = api.fetch_items(nums)

    if progress:
        progress("Формирую CSV…")
    csv_text = report.build_csv(nums, items, offset=offset)
    dst = unique_path(src.with_name(src.stem + "_unitrade.csv"))
    dst.write_bytes(csv_text.encode("utf-8"))
    found = sum(1 for n in nums if items.get(n))
    return {"dst": dst, "found": found, "total": len(nums)}


def open_file(path):
    try:
        os.startfile(str(path))  # noqa: S606  (Windows)
    except Exception:  # noqa: BLE001
        pass


def main():
    root = Tk()
    root.title("UNI — CSV по трек-номерам")
    root.geometry("480x150")
    lbl = Label(root, justify="center", wraplength=440, font=("Segoe UI", 10),
                text="Выберите файл со списком номеров\n(.xlsx, .csv или .txt)")
    lbl.pack(expand=True, padx=16, pady=12)
    root.update()

    src = filedialog.askopenfilename(parent=root, title="Файл со списком трек-номеров",
                                     filetypes=FILETYPES)
    if not src:
        root.destroy()
        return

    def show(text):
        lbl.config(text=text)
        root.update()

    try:
        res = process_file(src, progress=show)
    except importers.Unsupported as e:
        root.destroy()
        messagebox.showerror("Формат не поддерживается", str(e))
        return
    except Exception as e:  # noqa: BLE001
        root.destroy()
        messagebox.showerror("Не получилось",
                             "%s: %s\n\n%s" % (type(e).__name__, e,
                                               traceback.format_exc(limit=2)))
        return

    root.destroy()
    if messagebox.askyesno(
            "Готово",
            "Найдено %d из %d номеров.\n\nСохранено:\n%s\n\nОткрыть файл?" % (
                res["found"], res["total"], res["dst"])):
        open_file(res["dst"])


if __name__ == "__main__":
    main()
