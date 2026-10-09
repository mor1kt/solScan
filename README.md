# solana-scanner

Минимальный Python-проект для мониторинга мемкоинов на Solana с Telegram-уведомлениями.

## Запуск

Требуется Python 3.11 или новее.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env`, затем запустите сборщик:

```powershell
$env:PYTHONPATH = "src"
python src/main.py
```

В Linux/macOS используйте `source .venv/bin/activate`, а затем `PYTHONPATH=src python src/main.py`.
Если в Windows команда `python` недоступна, используйте путь к установленному интерпретатору Python 3.11+.

При запуске бот отправит сообщение `Бот запущен`, затем начнёт опрашивать DexScreener каждые 60 секунд. Остановка — `Ctrl+C`.

Сборщик использует публичные эндпоинты DexScreener без ключа: последние профили, boosts и подробности пар токена. URL и интервалы можно изменить переменными окружения или константами в `src/config.py`.

## Фильтры и статистика

Пороги дешёвых фильтров находятся в `config.yaml`: ликвидность, объём за час, возраст пары, покупки, отношение продаж к покупкам, market cap и FDV. Результаты каждой проверки сохраняются в таблицу `filter_results`, а статус токена — в `tokens.status`.

Посмотреть статистику можно так:

```powershell
python -m src.main stats
```

Команда показывает общее число собранных токенов, число отклонённых и причины отклонения.

## База данных

После первого цикла база будет сохранена в `data/solana_scanner.db`.

```bash
sqlite3 data/solana_scanner.db "SELECT mint, symbol, price_usd, liquidity_usd, volume_h1, dex_id FROM tokens ORDER BY last_processed_at DESC;"
```

Файл также можно открыть в любом SQLite-браузере.

## Скоринг и dry-run

Итоговый скор 0–100 и веса компонентов настраиваются в секции `scoring` файла `config.yaml`. В Telegram отправляются только токены выше `alert_threshold`. Повторный алерт возможен только после роста скора минимум на `repeat_score_delta` пунктов; история хранится в таблице `alerts`.

Для проверки полного цикла без отправки сообщений:

```powershell
python -m src.main --dry-run
```

## Результаты алертов

Для каждого отправленного алерта сохраняются цена и market cap, после чего worker проверяет результат через 15 минут, 1 час, 6 часов и 24 часа. Отчёт:

```powershell
python -m src.main report
python -m src.main report --by-score
```

Включить shadow-наблюдение за токенами, отсеянными фильтрами:

```yaml
shadow:
  enabled: true
```

В Telegram-команде `/stats` доступна короткая сводка по алертам.

## Security-проверки

После прохождения дешёвых фильтров токен проверяется бесплатными read-only запросами к RugCheck, Solana RPC и Jupiter Quote. Настройки находятся в секции `security` файла `config.yaml`. RPC URL можно заменить через `SOLANA_RPC_URL` в `.env`.

Результаты сохраняются в таблицу `security_results`, а итоговый статус токена обновляется в `tokens.status`.

## Оценка нарратива

Нарратив запускается только после прохождения дешёвых фильтров и security-проверок. Провайдер задаётся в `config.yaml`:

```yaml
narrative:
  provider: gemini
```

Ключи задаются в `.env` через `GEMINI_API_KEY` или `GROQ_API_KEY`. Если провайдер или ключ не настроен, токен получает статус `not_evaluated`, а сборщик продолжает работу. Результаты кэшируются в таблице `narrative_results`; пауза и дневной лимит настраиваются в секции `narrative`.

## Тесты

```powershell
pytest
```
