# portal-tg-guard.service: лимит стартов в секции `[Unit]` (инцидент BF-20261119-09)

- Канон: Р-121 (код выше документации), Р-109 (независимая приёмка на другой
  модели), Р-007 (правка пакета — зона Багфикса), Р-106 (инструкция владельцу —
  командами).
- Основание: рапорт УАС (письмо `db91bf533382`, ref
  `uas-stow-systemd-apply-done-1119`, 19.11) — после раскладки systemd-пакета
  `systemd-analyze verify` даёт
  `Unknown key 'StartLimitIntervalSec' in section [Service], ignoring`.
- Область: `systemd/.config/systemd/user/portal-tg-guard.service` (один файл
  пакета `systemd`), живая цель — `~/.config/systemd/user/portal-tg-guard.service`.

## Дефект

- **Symptom.** systemd не применяет `StartLimitIntervalSec=0` из юнита и
  пишет в проверке: `portal-tg-guard.service:17: Unknown key
  'StartLimitIntervalSec' in section [Service], ignoring`. Ограничение стартов
  не действует как задумано (юнит с `Restart=always` должен стартовать без
  лимита частоты), а предупреждение — «тихий» дефект: код возврата проверки
  остаётся 0.
- **Repro.** `systemd-analyze verify
  systemd/.config/systemd/user/portal-tg-guard.service` → строка с `Unknown
  key`; rc=0.
- **Root cause.** `StartLimitIntervalSec` — директива секции `[Unit]` (systemd
  ≥ 230; на хосте systemd 261). При переписывании юнита 30–31.10 ключ попал в
  `[Service]`, где systemd его игнорирует.

## Нормативные правила

1. `StartLimitIntervalSec` объявляется **только** в секции `[Unit]`.
2. Ключ присутствует в юните ровно один раз.
3. Значение и прочие директивы юнита правкой не меняются: перенос = одна
   удалённая строка и одна добавленная.

## Инварианты

- `systemd-analyze verify <файл пакета>` не выдаёт по этому файлу ни одного
  предупреждения (до правки — одно: `Unknown key`).
- Живой юнит после `systemctl --user daemon-reload` показывает
  `StartLimitIntervalUSec=0` — то есть директива **распознана**, а не
  проигнорирована.
- Прочие единицы пакета `systemd` не меняются (сверка пакета ↔ хост).

## Вне области

- **Включение** пяти новых юнитов (`homeostasis-ping.timer`,
  `owner-decision-ping.timer`, `portal-tg-guard.service`,
  `portal-tg-guard-watchdog.timer`, `sys-health.timer`) — отдельное решение
  владельца (enable — не мой ход).
- **Чистка застаревших `failed`-состояний** (`systemctl --user reset-failed`) —
  хост-состояние, отдельным ходом по решению владельца; к правке юнита не
  относится.
- `portal-tg-guard-watchdog.timer` и прочие сторожа — их правки в зоне УАС.

## Приёмка

1. `systemd-analyze verify systemd/.config/systemd/user/portal-tg-guard.service`
   → 0 предупреждений по файлу (до правки — 1).
2. `git show` коммита правки: изменена ровно одна директива, перенос 1→1,
   прочие строки юнита не тронуты.
3. `systemctl --user daemon-reload` → без ошибок;
   `systemctl --user show portal-tg-guard.service -p StartLimitIntervalUSec`
   → `0`.
4. Сверка «пакет ↔ хост» по `systemd/.config/systemd/user/` — расхождений нет.
5. Независимая приёмка: reviewer и verifier на моделях, отличных от модели
   автора и друг от друга (Р-109), на разных провайдерах.

## История

- 2026-11-19 — рапорт УАС (`db91bf533382`); инцидент BF-20261119-09; правка
  в ветке `task/fix-portal-tg-guard-startlimit-20261119`.
