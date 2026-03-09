### Сценарий 1: Скачать готовые субтитры (быстро, бесплатно, без GPU)

Большинство англоязычных YouTube-видео имеют автосгенерированные субтитры. Это самый быстрый путь.

```bash
Copy# Скачать субтитры одного видео
yt-dlp --write-auto-sub --sub-lang en --skip-download \
  --convert-subs srt \
  -o "%(title)s.%(ext)s" \
  -P ~/dotfiles/permaculture-os/03_Источники/.media/transcripts \
  "URL_ВИДЕО"
```

Что происходит: скачивает только субтитры (видео не качает), сохраняет в `.media/transcripts/` как `.srt` файл.

### Сценарий 2: Скачать аудио + транскрибировать Whisper (качество выше, работает офлайн)

Для видео без субтитров, или когда авто-субтитры плохие.

```bash
# Скачать только аудио
yt-dlp -x --audio-format mp3 \
  -o "%(title)s.%(ext)s" \
  -P ~/dotfiles/permaculture-os/03_Источники/.media/youtube \
  "URL_ВИДЕО"
```

Потом транскрибировать:

```bash
# Транскрипция через faster-whisper (использует GPU Quadro M2200)
faster-whisper "~/dotfiles/permaculture-os/03_Источники/.media/youtube/название.mp3" \
  --model medium --language en \
  --output_format srt \
  --output_dir ~/dotfiles/permaculture-os/03_Источники/.media/transcripts/
```

### Сценарий 3: Полный пайплайн одной командой

Создай скрипт `~/bin/perm-capture`:

```bash
#!/bin/bash
# perm-capture — захват YouTube видео в Permaculture OS
# Использование: perm-capture "URL" [тема]

URL="$1"
TOPIC="${2:-inbox}"
VAULT="$HOME/dotfiles/permaculture-os"
MEDIA="$VAULT/03_Источники/.media"
SOURCES="$VAULT/03_Источники/youtube"
DATE=$(date +%Y-%m-%d)

# Получаем метаданные видео
echo "📡 Получаю метаданные..."
TITLE=$(yt-dlp --get-title "$URL" 2>/dev/null)
CHANNEL=$(yt-dlp --print "%(channel)s" "$URL" 2>/dev/null)
DURATION=$(yt-dlp --print "%(duration_string)s" "$URL" 2>/dev/null)

# Безопасное имя файла
SAFE_TITLE=$(echo "$TITLE" | tr '/' '_' | tr ':' '-' | head -c 80)

echo "📺 $TITLE"
echo "📡 $CHANNEL"
echo "⏱  $DURATION"

# Скачиваем субтитры
echo "📝 Скачиваю субтитры..."
yt-dlp --write-auto-sub --sub-lang en --skip-download \
  --convert-subs srt \
  -o "$MEDIA/transcripts/$SAFE_TITLE.%(ext)s" \
  "$URL" 2>/dev/null

# Проверяем, скачались ли
TRANSCRIPT="$MEDIA/transcripts/$SAFE_TITLE.en.srt"
HAS_SUBS="false"
if [ -f "$TRANSCRIPT" ]; then
  HAS_SUBS="true"
  echo "✅ Субтитры получены"
else
  echo "⚠️  Субтитры не найдены. Используй perm-whisper для транскрипции."
fi

# Создаём заметку-источник
NOTEFILE="$SOURCES/src_${SAFE_TITLE// /_}.md"
cat > "$NOTEFILE" << EOF
---
type: источник
format: youtube
title: "$TITLE"
url: "$URL"
channel: "$CHANNEL"
duration: "$DURATION"
language: en
topics: [$TOPIC]
status: inbox
date_added: $DATE
date_processed: 
has_transcript: $HAS_SUBS
---

# $TITLE

## Зачем я это сохранил


## Ключевые идеи
1. 
2. 
3. 

## Привязка к темам
- [[]]

## Цитаты / таймкоды


## Статус обработки
- [ ] Просмотрено
- [ ] Ключевые идеи извлечены
- [ ] Привязано к теме
- [ ] Переработано в тему
EOF

echo "📄 Заметка создана: $NOTEFILE"
echo ""
echo "Следующие шаги:"
echo "  1. Открой заметку в Obsidian"
echo "  2. Посмотри видео"
echo "  3. Заполни 'Зачем я это сохранил' и 'Ключевые идеи'"
if [ "$HAS_SUBS" = "true" ]; then
  echo "  4. Транскрипт: $TRANSCRIPT"
fi

```

Сделай исполняемым:

```bash
chmod +x ~/dotfiles/scripts/.local/bin/perm-capture
# Убедись что ~/bin в PATH:
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Как использовать — простая модель:

```bash
# Нашёл видео → одна команда
perm-capture "https://www.youtube.com/watch?v=xxxxx"

# С указанием темы
perm-capture "https://www.youtube.com/watch?v=xxxxx" "почва"
```

Результат: в `03_Источники/youtube/` появляется готовая заметка с метаданными. Открываешь в Obsidian, смотришь видео, заполняешь.

### Как использовать — продвинутая модель:

```bash
Copy# 1. Захват
perm-capture "https://www.youtube.com/watch?v=xxxxx" "зоны"

# 2. Если нужен транскрипт для перевода/анализа — копируешь текст субтитров
cat ~/dotfiles/permaculture-os/03_Источники/.media/transcripts/название.en.srt

# 3. Несёшь транскрипт ко мне в чат:
#    "Вот транскрипт видео про зоны пермакультуры. 
#     Извлеки 5 ключевых идей, переведи на русский, 
#     привяжи к теме Зоны_и_сектора."

# 4. Я возвращаю структурированный текст → ты вставляешь в заметку
```