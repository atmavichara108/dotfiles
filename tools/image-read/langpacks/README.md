# image-read langpacks (tesseract traineddata)

Языковые пакеты tesseract для локального OCR фичи image-read (Stage 1).
Размещение в dotfiles — решение владельца O1 (letter-meta-vision-go, 2026-10-17):
пакеты живут в репо `tools/image-read/langpacks/`, **без root** (никаких
`apt install tesseract-ocr-*` / `pacman` — системные правки вне зоны агента).

## Состав

| Файл | Назначение |
|---|---|
| `eng.traineddata` | язык eng (терминальные скриншоты, лог) |
| `rus.traineddata` | язык rus (русские строки скриншотов) |
| `configs/tsv` | конфиг TSV-режима: `tessedit_create_tsv 1` (бэклок, см. ниже) |
| `SHA256SUMS` | контрольные суммы всех 4 файлов каталога |

## Provenance

- Источник: `https://github.com/tesseract-ocr/tessdata_fast` (ветка `main`).
- Лицензия: **Apache-2.0** (tesseract-ocr).
- Скачаны: 2026-10-18.
- Версия tesseract хоста: 5.5.3.

## Целостность

```
cd tools/image-read/langpacks && sha256sum -c SHA256SUMS
```

Значения sha256 (сверить при пересборке):
- `eng.traineddata`  `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`
- `rus.traineddata`  `e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225`

## Почему в репо (решение O1, без root)

Системный `apt`/`pacman` ставит traineddata в `/usr/share/tessdata/` и требует
root — это вне зоны агента (и ломает воспроизводимость). Поэтому пакеты
самодостаточны в dotfiles: `image-read.py` ищет каталог traineddata в порядке
`$IMAGE_READ_TESSDATA` → **`<repo>/tools/image-read/langpacks`** →
`~/.local/share/tessdata` → `/usr/share/tessdata`. Первый каталог с **всеми**
запрошенными языками побеждает. Через stow-симлинк `~/.local/bin/image-read.py`
репозиторий резолвится по `realpath(__file__)`, так что пакеты находятся
автоматически.

## configs/tsv — бэклок TSV-режима (обязателен)

`tesseract 5.5.3` с `--tessdata-dir <dir>` ищет конфиги (в т.ч. `tsv`) **в
`<dir>/configs/`**, а не в системном `/usr/share/tessdata/configs/`. В чистых
`tessdata_fast`-каталогах папки `configs/` нет, поэтому TSV-режим
(`tesseract … tsv`, который использует `image-read.py` для layout/full)
молча деградирует: `read_params_file: Can't open tsv` → plain-text вывод
вместо TSV (либо rc=1) → layout/full не работают.

Фикс: дословная копия системного `/usr/share/tessdata/configs/tsv`:

```
tessedit_create_tsv 1
```

Без `configs/tsv` Stage 1 из коробки сломан в режимах `layout`/`full`;
`text`-режим не зависит от этого файла.

## Использование

```
image-read.py <скрин.png> --mode full --langs eng+rus --json
```

OCR — локальный, без сети и LLM (Stage 1-3). Vision-слой (Stage 4) — только по
отдельному решению владельца (O2) + ADR; байты изображения не покидают машину.
