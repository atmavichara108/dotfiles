# mail-hub — корпоративная почта re-search.wiki на ноутбуке (v0.3, нулевой бюджет)

Канон: `~/Projects/mail-hub-handoff.md` (v0.2 + приложение v0.3 ЦУ).
Архитектура (A3/A4): MX-приёмник — внешний (Forward Email Free → пересылка
на существующий ящик); ноут — клиент, Maildir-архив, отправка.

## Что здесь

- `mbsyncrc.example`, `msmtprc.example` — шаблоны; живые `~/.mbsyncrc` и
  `~/.msmtprc` создаются с правами 600, секреты — ВНЕ репо
  (`~/.secrets/mail-hub/`, файлы 600, PassCmd).
- `scripts/.local/bin/mail-hub-sync` — IMAP → Maildir (обёртка mbsync).
- `scripts/.local/bin/mail-hub-send` — отправка через msmtp; нет релея →
  письмо ждёт в outbox, «отправлено» = 250 (A6).
- `scripts/.local/bin/mail-hub-outbox-flush` — очередь уходит при подключении.

## Порядок запуска (DoD «сегодня»)

1. Пакеты (владелец): `sudo pacman -S isync msmtp`.
2. Заполнить `~/.mbsyncrc` (IMAP ящика-приёмника) и `~/.secrets/mail-hub/imap.pass`.
3. Владелец: DNS по приложению v0.3-V4 (MX/TXT Forward Email + alias).
4. `mail-hub-sync` → письмо с чужого адреса появляется в `~/Mail/re-search.wiki/`.
5. Отправка — по развилке V2: (а) Gmail Send-As — настройка у владельца;
   (б) msmtp порт 25 — конфиг + честный Junk-риск (PBL, A4b);
   (в) FE Enhanced $3/мес — позже, апгрейдом без миграции.

## Гейты

- Секреты не в git и не в логах (маскирование — A6).
- DNS-записи вставляет только владелец (B1–B4: ничего не удалять!).
- Прогрев нового домена: 5–10 писем/день, без массовых рассылок (A4b).
- Приём почты напрямую на ноут невозможен (A2 — физика, не философия).
