---
type: Incident
title: "Канальный дрейф: 18 писем sent без следа у получателя + 13 висячих claims вне реестра"
status: open (лечение — по владельцу/ЦУ; зафиксировано как класс, без травмы)
timestamp: 2026-10-30
ref: sign-rules-to-infra (ЦУ 2026-10-30)
---

# INC-25: канальный дрейф (класс INC-21)

## Symptom
Первый прогон осей дрейфа (session-cop + watch-logs): 18 писем за окно
(последние 40) ушли (sent/queued) без следа у получателя (read-gate sqlite —
session_message не содержит их message-id); 13 уникальных активных claims
(ses_* и легаси-id) вне peer-registry.

## Root cause
Классы, не единичный сбой:
1. Канал: sent в журнале отправителя ≠ delivered у получателя — ровно INC-21
   («sent без доказательства») в новой инструментальной видимости. Часть —
   письма в мёртвые сессии (инцидент фантомов, INC-18), часть — таймауты
   очереди, у которых след не сохранился.
2. Claims: легаси-id стиля (sysop-dotfiles-20261006, librarian-vault-...) и
   живые сессии вне реестра (maya-lint v2/handshake, whitelist-config,
   adr-shadow-classifier ×3, model-watch) — реестр отстаёт от claims.

## Fix (что сделано)
- Оси дрейфа 1–2 в watch-logs (60с) — ловим без копа; дедуп по хешу.
- Канон правил знаков (tools/peer-comms/sign-rules.md).
- 13 висячих claims внесены в waits-реестр как осознанные ожидания (TTL 48ч):
  лечение — либо реестр догоняет claim, либо claim истекает; разбор —
  по владельцу/ЦУ, не молчаливая чистка.
- Baseline зафиксирован как шкала (sent 411 / delivered 7 / timeout 105 /
  failed 18 / dead-letter 2; queued 106 / requeued 16 / agent-fallback 18).

## Evidence
- ~/.local/state/opencode/cop/incidents.jsonl (оси: channel 18, claims 13);
- ~/.local/state/opencode/watch/incidents.jsonl (drift-находки);
- waits.jsonl — 13 записей «висячий claim …».
