---
type: Spec
kind: artifact
project: dotfiles
title: "L9 — реестр GGUF-конвертеров multilingual-e5-small"
status: final
timestamp: 2026-10-17
owner: Ability Lab
related:
  - "docs/specs/lab-protocol-l9.md"
  - "docs/specs/lab-l9-diag-iteration1.md"
---

# Реестр конвертеров (по решению ЦУ l9-iter2-decision-20261017)

| конверт | автор/конвертер | дата | вердикт испытания | статус |
|---|---|---|---|---|
| multilingual-e5-small-Q8_0.gguf | keisuke-miyako («Tmp»), q8_0 | 2026-02-03 | RU-vocab рассинхрон (diag6c), вырожденное пространство | **risk ×1** |
| multilingual-e5-small-F16.gguf | keisuke-miyako («Tmp»), f16 | 2026-03-03 | тот же дефект RU-vocab (iter2 мин. тест) | **risk ×2** |
| multilingual-e5-small-f16.gguf | hdrrayan, f16 | 2026-09-17 | семантика живая: лестница правильная, негативы чистые, kill по переводу PASS | **ok (активная)** |
| multilingual-e5-small-q8_0.gguf | TwinSunsLLC, q8_0 | 2026-08-14 | не испытан | **запас (план Б)** |

Прочие найденные и отсеянные по критериям ЦУ: rodion-m (2024, старый),
milimyname (2026-03, не испытан, после keisuke — рискованный автор не
подтверждён), jc-lab (ko-v2, основа dragonkue — корейская специализация, не
multilingual-e5-small базовый).

## Правило

Перед подключением любого GGUF-конверта — минимальный тест
(`tools/lab-l9/iter2_minimal_test.py`): round-trip кириллицы + 6 скалярных
косинусов; kill: перевод en↔ru НЕ выше нерелевантной RU-пары. Результат —
строка в этом реестре.
