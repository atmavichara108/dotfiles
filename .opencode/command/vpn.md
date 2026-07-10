---
description: Пайплайн настройки VPN для текущей системы. Аудит → проектирование → реализация → проверка.
agent: builder
subtask: true
---

# Пайплайн: Настройка VPN

## Контекст

Задача Макса: решить вопрос с VPN — это приоритет №1, блокирует важную задачу.
Система: Manjaro Linux, Qtile (X11), NVIDIA.
Уже установлены: `hiddify-bin`, `tor`, `torsocks`, `proxychains-ng`, `obfs4proxy`.

## Требования

- Рабочее VPN-соединение на Manjaro (Arch Linux)
- Минимальная нагрузка на систему
- Поддержка kill-switch (без утечек)
- Интеграция с Qtile (простой toggle/статус)
- Никаких секретов в репо

## Шаги

### Шаг 1: Аудит текущего VPN-стека
Вызови `sysop` для аудита сети:
- `ip addr` — сетевые интерфейсы
- `ip route` — таблица маршрутизации
- `systemctl list-units --type=service --state=running | grep -iE "vpn|wireguard|openvpn|tun"` — VPN-сервисы
- `cat /etc/resolv.conf` — текущий DNS
- `ping -c 1 1.1.1.1` — проверка соединения
- `which wg-quick openvpn hiddify-cli` — какие клиенты установлены

### Шаг 2: Проектирование решения
Оцени варианты:
1. **WireGuard** — нативный, быстрый, современный протокол. wg-quick.
   - Плюсы: скорость, минимализм, ядро Linux
   - Минусы: нужен конфиг-файл от провайдера
2. **OpenVPN** — уже есть `networkmanager-openvpn`. Стандартный.
   - Плюсы: совместимость, GUI через NM
   - Минусы: медленнее WireGuard
3. **hiddify** — уже установлен. Мульти-протокол.
   - Плюсы: уже стоит, много протоколов
   - Минусы: GUI, не terminal-native
4. **proxychains + Tor** — уже настроено (tor на 9050).
   - Плюсы: анонимность, уже работает
   - Минусы: медленно, не весь трафик

Выбери оптимальное решение и обоснуй.

### Шаг 3: Реализация
Вызови bash-dev для создания скриптов/конфигов:
```
task(agent="bash-dev", prompt="Настройка VPN на Manjaro: [выбранное решение]. 
  - Конфиги в dotfiles/vpn/
  - Скрипты для up/down/toggle/status
  - Интеграция с Qtile (виджет статуса)
  - Kill-switch
  - Без секретов в репо (шаблон конфига + README)")
```

### Шаг 4: Проверка
Вызови reviewer:
```
task(agent="reviewer", prompt="review: VPN-конфигурация. 
  - Проверь безопасность
  - Проверь отсутствие секретов
  - Проверь kill-switch
  - Проверь интеграцию с Qtile")
```

### Шаг 5: Документирование
- `dotfiles/vpn/README.md` — как подключиться
- `docs/cheatsheets/vpn.md` — быстрые команды
- Git-commit: `feat(vpn): add VPN configuration [выбранное решение]`

## DoD

- [ ] VPN поднимается и работает
- [ ] Kill-switch активен (проверено: утечек нет)
- [ ] Qtile-виджет показывает статус
- [ ] Скрипты лежат в `dotfiles/vpn/`
- [ ] All good in `stow vpn -n`
- [ ] README с инструкцией
- [ ] No secrets in repo
