# Бот без компьютера — подробная инструкция (GitHub Actions)

## Как это будет работать

```
Telegram (вы)  →  GitHub Actions (каждые 5 минут)  →  api.unitrade.space
                          ↓
                 CSV-файл обратно в Telegram
```

Ваш ПК может быть выключен — бот живёт в облаке GitHub.
Ответ приходит **с задержкой до ~5–10 минут** (ограничение расписания GitHub).

---

## Шаг 0. Обязательно: остановите бота на своём ПК

Telegram разрешает боту только **одно** подключение. Если локальный бот работает,
облачный получит ошибку `Conflict: terminated by other getUpdates request` и не ответит.

1. Двойной клик **`stop_bot.bat`** → должно появиться `Остановлен PID ...`
2. Проверка: напишите боту — он больше не отвечает (это правильно).

---

## Шаг 1. Создайте репозиторий

1. Откройте <https://github.com/new>
2. **Repository name**: `unitrade-bot`
3. Выберите **Public** (важно — см. раздел «Лимиты»)
4. Галочки *Add a README* / *.gitignore* / *license* — **не ставьте**
5. **Create repository**

---

## Шаг 2. Загрузите файлы

На странице пустого репозитория: **Add file → Upload files** → перетащите файлы → **Commit changes**.

### Обязательные файлы

| Файл | Зачем нужен |
|---|---|
| `bot.py` | сам бот |
| `trackers.py` | запросы к `api.unitrade.space` |
| `trackers.txt` | список источников (`unitrade`, `track24`) |
| `report.py` | формирование CSV (10 этапов) |
| `importers.py` | чтение `.txt` / `.csv` / `.xlsx` |
| `requirements.txt` | зависимости (`requests`, `openpyxl`) |
| `README.md` | описание (по желанию) |

### Тоже можно загрузить (не мешают)

`make_csv.py`, `pick_file.py`, `numbers.txt`, `.env.example`, `token.txt.example`,
`.gitignore`, `run_pick.bat`, `run_csv.bat`, `run_bot.bat`, `stop_bot.bat`, `stop_bot.ps1`

### ⛔ НЕ загружайте

| Файл | Почему |
|---|---|
| **`token.txt`** | это пароль бота — попадёт в публичный репозиторий |
| `unitrade.csv` | личные результаты |
| `bot.log`, `bot.err`, `bot_state.json` | служебные, создаются сами |
| `__pycache__/`, `.venv/` | мусор |

> ⚠️ Файл `.gitignore` защищает только при работе через `git` в консоли.
> При загрузке через браузер он **ничего не фильтрует** — следите за списком руками.

### 2.1. Файл расписания `.github/workflows/bot.yml` — отдельным шагом

Папку, имя которой начинается с точки, браузер при загрузке часто не показывает.
Поэтому создайте файл прямо на сайте:

1. **Add file → Create new file**
2. В поле имени введите **ровно** это (после каждого `/` GitHub сам создаст папку):

   ```
   .github/workflows/bot.yml
   ```
3. Вставьте содержимое:

```yaml
name: UNI bot (poll)

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: unitrade-bot
  cancel-in-progress: false

jobs:
  poll:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install --quiet -r requirements.txt

      - name: Poll Telegram updates
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          ALLOWED_CHAT_IDS: ${{ secrets.ALLOWED_CHAT_IDS }}
        run: python bot.py --once

      - name: Commit offset
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if [ ! -f bot_state.json ]; then
            echo "bot_state.json ещё не создан"
            exit 0
          fi
          git add -f bot_state.json
          if git diff --cached --quiet; then
            echo "offset без изменений"
            exit 0
          fi
          git commit -q -m "chore: update bot offset"
          for i in 1 2 3; do
            git push && break
            git pull --rebase -q || true
            sleep 3
          done
```

4. **Commit changes**

---

## Шаг 3. Добавьте токен в «секреты»

1. В репозитории: **Settings** (шестерёнка сверху)
2. Слева: **Secrets and variables → Actions**
3. Кнопка **New repository secret**
4. **Name**: `BOT_TOKEN`
5. **Secret**: вставьте токен (`8992253804:...`) — без кавычек и пробелов
6. **Add secret**

> Секреты GitHub шифруются и не видны в коде и логах — даже в публичном репозитории.

### (необязательно, но рекомендуется) ограничить доступ

Чтобы ботом пользовались только вы:

1. В Telegram отправьте боту **`/id`** → он ответит `Ваш chat id: 123456789`
2. **Settings → Secrets and variables → Actions → New repository secret**
3. **Name**: `ALLOWED_CHAT_IDS`, **Secret**: `123456789`
4. Несколько человек — через запятую: `123456789,987654321`

Если этот секрет не создан — бот отвечает **любому**, кто его найдёт.

---

## Шаг 4. Разрешите workflow писать в репозиторий

Нужно, чтобы бот запоминал, какие сообщения уже обработаны (`bot_state.json`),
иначе он будет отвечать на одно и то же каждые 5 минут.

1. **Settings → Actions → General**
2. Прокрутите до **Workflow permissions**
3. Выберите **Read and write permissions**
4. **Save**

---

## Шаг 5. Включите Actions (если попросит)

Вкладка **Actions** вверху. Если видите кнопку
*«I understand my workflows, go ahead and enable them»* — нажмите её.

Слева должен появиться workflow **UNI bot (poll)**.

---

## Шаг 6. Первый запуск

1. Вкладка **Actions** → слева **UNI bot (poll)**
2. Справа **Run workflow** → **Run workflow**
3. Через ~20–40 секунд обновите страницу — появится запуск
4. Откройте его → шаг **Poll Telegram updates** → там должно быть:

   ```
   Активные сайты: unitrade API, track24.ru
   ```

   Ошибок (`Error`, `Traceback`) быть не должно.

## Шаг 7. Проверка в Telegram

1. Напишите боту **`/start`** — должна прийти справка.
2. Отправьте номера **текстом** — в течение ~5–10 минут придёт
   «Обрабатываю N номеров…» и **CSV-файл**.
3. Отправьте **Excel** (скрепка → файл) — должен прийти CSV.

Хотите проверить сразу, не ожидая расписания: после отправки сообщения
нажмите **Actions → UNI bot (poll) → Run workflow**.

---

## Что происходит каждые 5 минут

1. GitHub поднимает виртуалку Ubuntu (~20 сек).
2. Ставит Python 3.12 и зависимости (`requests`, `openpyxl`).
3. `python bot.py --once` — забирает **новые** сообщения из Telegram.
4. Отвечает: `/start` → справка; файл → скачивает, разбирает номера, спрашивает
   `api.unitrade.space`, формирует CSV и отправляет файлом.
5. Запоминает позицию в `bot_state.json` и коммитит её — чтобы не отвечать повторно.
6. Виртуалка уничтожается (ваш ПК не участвует).

---

## Лимиты и подводные камни

| Что | Значение | Что делать |
|---|---|---|
| Минимальный шаг расписания | 5 минут | ответ с задержкой до 5–10 мин — это норма |
| Точность cron у GitHub | в часы пик задержка до 15–20 мин | подождите или жмите Run workflow |
| Минуты Actions на **приватном** репо | 2000/мес — не хватит | сделайте репозиторий **Public** |
| Минуты Actions на **публичном** репо | бесплатно и без лимита | рекомендуемый вариант |
| Простой репозитория 60 дней | расписание отключается | раз в 2 месяца жмите Run workflow |
| Один бот = одно подключение | иначе `Conflict` | локальный бот должен быть выключен |
| `api.unitrade.space` | ~1 запрос/сек | бот сам делает паузы |
| Размер файла | до 20 МБ | больше — бот предупредит |

**Почему Public.** Расписание «каждые 5 минут» — это ~288 запусков в сутки,
каждый тарифицируется минимум как 1 минута → ~8600 минут в месяц, а на приватных
репозиториях дают 2000. На публичных Actions бесплатны.
Токен хранится в Secrets, трек-номера в логи не пишутся — секретов в коде нет.

---

## Если что-то пошло не так

| Симптом | Причина | Что делать |
|---|---|---|
| В логе `Conflict: terminated by other getUpdates request` | работает второй экземпляр бота | `stop_bot.bat` на ПК; отключите другие деплои |
| `Не задан токен` | секрет не создан или имя с опечаткой | имя должно быть ровно `BOT_TOKEN` |
| Шаг `Commit offset` упал с `403` | нет прав на запись | Шаг 4: **Read and write permissions** |
| Всё зелёное, но бот молчит | включён `ALLOWED_CHAT_IDS`, а вас в списке нет | в логе строка «Сообщение из неразрешённого чата …» → добавьте свой id |
| `Не удалось скачать файл` | файл больше 20 МБ | разбейте на части |
| CSV пришёл, но строки пустые | номера не распознались | номер ≥ 6 символов: латиница, цифры, дефис |
| Расписание не срабатывает | Actions отключились после простоя | Actions → Run workflow (и держите репозиторий «живым») |
| Ответ приходит дважды | не сохранился `bot_state.json` | проверьте Шаг 4 и что файл появился в репозитории |

---

## Обслуживание

- **Обновить код**: *Add file → Upload files* тем же именем — GitHub перезапишет.
- **Логи**: вкладка *Actions* → нужный запуск → шаг *Poll Telegram updates*.
- **Поставить на паузу**: *Actions → UNI bot (poll) → ⋯ → Disable workflow*.
- **Вернуться на свой ПК**: Disable workflow, затем `run_bot.bat`.
- После первого успешного запуска в репозитории появится `bot_state.json` — это нормально.

---

## Чек-лист

- [ ] Локальный бот остановлен (`stop_bot.bat`)
- [ ] Репозиторий создан и он **Public**
- [ ] Загружены обязательные файлы (7 шт.)
- [ ] Создан `.github/workflows/bot.yml`
- [ ] Секрет `BOT_TOKEN` добавлен
- [ ] Workflow permissions = **Read and write**
- [ ] `Run workflow` прошёл без ошибок
- [ ] `/start` отвечает
- [ ] Excel → CSV приходит
- [ ] (по желанию) добавлен `ALLOWED_CHAT_IDS`


