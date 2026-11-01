# Handoff 2026-11-01 — Qtile: зависание переключения групп/тайлов

## Симптом (слово владельца)

Владелец сообщил в Капитанский портал:
- «Что происходит с моим ноутбуком? Все зависло, я не могу переключаттся между
  тайлами и рабочими пространствами»;
- затем: «Перезагрузил кьютил и все пришло в норму».

## Evidence

`~/.local/share/qtile/qtile.log` содержит цепочку:

- `KB command error toggle_group: AttributeError: 'NoneType' object has no
  attribute 'get_layering_information'`
- `KB command error toscreen: AttributeError: 'NoneType' object has no
  attribute 'get_layering_information'`
- далее в poll-loop:
  `PropertyNotify -> update_state -> fullscreen -> change_layer ->
  group_bar.window.get_layering_information()` где `group_bar.window` == `None`.

Отдельная повторяющаяся ошибка:

- `libqtile mpris2widget.py:_config_async(): Unable to add signal receiver for
  Mpris2 players`
- `dbus_fast.errors.InvalidBusNameError: invalid bus name: chromium`

## Гипотеза

Наиболее вероятный механизм зависания навигации — падение qtile в X11-пуле при
обновлении состояния окна: `group_bar.window` оказался `None`, а код
`libqtile/backend/x11/window.py` вызвал у него метод без проверки. Это ломает
именно `toggle_group` и `toscreen`, что совпадает с симптомом. Перезапуск qtile
обнуляет состояние и восстанавливает объект бара.

Ошибка `chromium` через MPRIS2 — отдельная проблема некорректного DBus-имени
медиаплеера; она повторяется, но заявленный симптом переключения не объясняет
напрямую.

## Статус

- Владельцем выполнено: `qtile` перезапущен → состояние восстановлено.
- Инцидент по сценарию пользователя закрыт как resolved-workaround.
- Корневая причина не доказана до правки; нужен прогон на qtile-dev.

## Следующие шаги

1. На воспроизведение/анализ отдать `qtile-dev`.
2. Проверить, связано ли `group_bar.window=None` с падением/сменой окна бара
   после мультимониторного события или полноэкранного окна.
3. Отдельно: обработать MPRIS2-шум `chromium`.
4. Без подтверждения владельца не менять конфиг qtile.
