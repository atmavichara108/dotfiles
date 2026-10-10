# INCIDENT: tool_choice роняет спавн субагента — закрыт существующим шим-фиксом

- Дата: 2026-10-10, сессия sysop (dotfiles, исполнение ssa-спек).
- Статус: закрыт, фикс уже в HEAD (`d6446f5`), дублирующий фикс не требуется.

## Symptom

Первый вызов `task(agent=builder)` упал до старта субагента:

```text
Subagent failed (sessionID: ses_ed9f0a108ffeyfZZYysnsEkvRP):
only `"auto"` is supported for `tool_choice`.
`"none"`, `"required"`, and named function choices are not currently supported
```

## Repro

- Тот же вызов с тем же промптом, повторённый сразу же, — успех
  (`ses_ed9ef4d23ffeOuZIrFCqMo0LML`, control-harness выполнен полностью).
- Всего за сессию: 1 падение из ~8 subagent-вызовов (builder ×3, reviewer ×1,
  verifier ×3 — у verifier были только лимиты шагов, не tool_choice).

## Root cause

Шлюз `api.justwoker.icu` поддерживает только `tool_choice:"auto"`;
OpenCode/AI SDK форсирует инструмент при спавне субагента (none/required/named)
— ход ронялся. Падение произошло до того, как нормализация живьём подхватилась
сессией; повтор прошёл.

## Fix (существующий, не мой)

`d6446f5 fix(shim): normalize tool_choice -> auto перед форвардом upstream`
(`opencode-global/.config/opencode/shim/justwoker-shim.ts`, +17):
стрим и non-stream + OpenAI-фасад, тело пере-сериализуется только при изменении.
Покрывает ровно этот симптом (текст ошибки совпадает дословно).

## Evidence

- Ошибка и sessionID падения: выше.
- Успешный повтор: `ses_ed9ef4d23ffeOuZIrFCqMo0LML`.
- Фикс в истории текущей ветки: `git show d6446f5 --stat`.

## Открытое (не блокер)

- Если падение повторится ПОСЛЕ полного рестарта сессии с шимом в HEAD —
  переоткрыть как новый инцидент (возможно, путь без нормализации).
- Verifier дважды упирался в лимит шагов на ровном месте — отдельное
  наблюдение, не часть этого инцидента.
