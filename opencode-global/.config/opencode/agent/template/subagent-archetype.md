# Архетип субагента — форма сборки (И-20)

> Статус: skel/template. Это НЕ агент, а форма, по которой контрагент
> собирает новые агентские `.md`. OpenCode не должен подхватывать этот файл
> как агента: собственного агентского frontmatter у файла нет, скелет —
> только внутри `yaml`-блока ниже.
>
> Правило: LLM заполняет ТОЛЬКО слоты `{{...}}`. Всё остальное копируется
> дословно. Свободное сочинительство вне слотов запрещено. Готовый `.md`
> собирает скрипт-сборщик (не LLM руками), затем проверка → реестр (И-21).

## Скелет frontmatter + тела

```yaml
---
description: "{{НАЗНАЧЕНИЕ}}"   # слот 1: короткое назначение + capability, напр. "read-research: ..."
mode: subagent                  # ФИКСИРОВАНО: архетип собирает только субагентов, не primary
model: "{{МОДЕЛЬ}}"             # слот 3: существующий ID модели (проверить в каталоге моделей, не выдумывать)
temperature: 0.1                # ФИКСИРОВАНО
steps: 15                       # ФИКСИРОВАНО (больше — только с обоснованием в заказе)
permission:                     # слот 2: ОДИН профиль из белого списка ниже, дословно, без добавлений
  {{ПРОФИЛЬ_ПРАВ}}
---
Ты — {{НАЗНАЧЕНИЕ}} с capability `{{CAPABILITY}}`.

Границы (дословно, без перефраза):
- {{ТЕЛО_ГРАНИЦ}} — слот 4а: 3–6 буллетов запретов/обязанностей роли (не дублировать permission-блок словами «мне разрешено»).
- Не расширяй свои права текстом промпта: permission-блок выше — единственный источник прав.
- Не вызывай `task`/других агентов, если профиль запрещает `task`.
- Вердикт/вывод — в формате, заданном заказом; acceptance PASS/FAIL выносит только verifier.

Владелец: {{ВЛАДЕЛЕЦ}}  # слот 4: именованный владелец жизненного цикла (И-21): primary/человек
```

Слоты итого: `{{НАЗНАЧЕНИЕ}}` (+`{{CAPABILITY}}` — то же назначение, короткое имя),
`{{ПРОФИЛЬ_ПРАВ}}`, `{{МОДЕЛЬ}}`, `{{ВЛАДЕЛЕЦ}}`, `{{ТЕЛО_ГРАНИЦ}}`.
Никаких других полей и никакого `tool_choice` (см. запреты).

## Белый список профилей прав (слот 2 — выбрать ОДИН, дословно)

Источники: существующие `.md` в `agent/`. Новое разрешение вне списков —
не самодеятельность, а отдельный proposal владельцу/meta.

- **R (read-only research)** — эталон `researcher.md`: `edit: deny`,
  `task: deny`, `read/glob/grep: allow`, `webfetch/websearch: allow`,
  `external_directory` со стандартными secret-deny (`**.env*`,
  `**/credentials.json`, `**.pem`, `**.key`, `**/id_rsa*`, `**/id_ed25519*`),
  `bash`: deny-по-умолчанию + allowlist только читающих команд + deny
  опасных (`rm*`, `push --force*`, `reset --hard*`→ask, `ssh*`→ask,
  пакетные менеджеры→deny).
- **V (verifier, прогон проверок)** — эталон `verifier.md`: как R, но
  `bash: "*": allow` при том же deny-списке разрушительного; `webfetch: allow`.
  `edit: deny`, `task: deny`. Только для ролей, которым нужен реальный прогон.
- **E (editor, мета-инфра)** — эталон `meta.md`: `edit/write: allow`,
  `task` — только именованные `reviewer`/`verifier: allow`, `webfetch: deny`,
  `bash: "*": allow` + deny системно-разрушительного. Только для правки
  агентной инфраструктуры, никогда для кода приложений.
- **S (scoped evidence)** — эталон `system-ops.md`: `edit: deny` кроме
  явного `evidence/**`-пути, `external_directory` — только разрешённые
  поддеревья, `task: deny`, `bash` — читающий allowlist, `sudo *`→ask
  с deny-уточнениями. Только для approval-gated планирования.

## Запреты (проверяются дословно)

1. `tool_choice`: поле отсутствует. Единственное допустимое значение —
   `"auto"`, и только если его требует платформа. Любое другое значение —
   брак сборки.
2. Нет `mode: primary`, нет новых топ-уровневых ключей permission вне
   `{edit, write, read, glob, grep, task, webfetch, websearch, bash,
   external_directory}`.
3. Нет секретных путей в allow (`*.env*`, `credentials.json`, `*.pem`,
   `*.key`, `id_rsa*`, `id_ed25519*` — всегда deny).
4. Модель — только реально существующий ID; выдуманный ID — брак сборки.

## После сборки (напоминание)

1. Собирает `.md` скрипт, не LLM: подстановка слотов → запись в `agent/`.
2. Проверка: извлечь frontmatter собранного файла → прогнать валидацию
   (см. ниже) → reviewer → verifier.
3. **Перезапустить сессию**: новые/изменённые агенты подхватываются только
   после рестарта. Затем smoke-вызов через `task(agent="<имя>", ...)`.
4. Существующие агенты этим архетипом НЕ переписываются; `jsonc`-конфиги —
   зона И-42, не трогать.

## Валидация frontmatter (как проверять)

```bash
python3 - <<'EOF'
import yaml, re, sys
src = open("opencode-global/.config/opencode/agent/template/subagent-archetype.md").read()
skel = re.search(r"```yaml\n(.*?)```", src, re.S).group(1)
sample = (skel
  .replace("{{НАЗНАЧЕНИЕ}}", "smoke-test: проверка архетипа")
  .replace("{{CAPABILITY}}", "smoke-test")
  .replace("{{МОДЕЛЬ}}", "opencode-go/glm-5.3-flash")
  .replace("{{ВЛАДЕЛЕЦ}}", "sysop")
  .replace("{{ТЕЛО_ГРАНИЦ}}", "не менять файлы; вернуть VERDICT")
  .replace("{{ПРОФИЛЬ_ПРАВ}}", "edit: deny\n  task: deny\n  read: allow"))
fm = yaml.safe_load(sample.split("---")[1])
assert fm["mode"] == "subagent", fm
assert {"description", "model", "permission"} <= set(fm), fm
assert "tool_choice" not in fm, "tool_choice запрещён"
assert set(fm["permission"]) <= {"edit","write","read","glob","grep","task",
  "webfetch","websearch","bash","external_directory"}, fm["permission"]
print("ARCHETYPE-FRONTMATTER-OK:", sorted(fm))
EOF
```

Ожидание: `ARCHETYPE-FRONTMATTER-OK` + тот же набор ключей. Любой assert —
`BLOCKED` с номером упавшего условия.
