#!/usr/bin/env python3
"""captain-panel-asr-worker — локальная транскрипция для бот-пульта.

Запускается ТОЛЬКО через локальный venv faster-whisper. Печатает одну
машиночитаемую строку `ASR_JSON {...}` и ничего секретного.
"""
import json
import sys
import time

from faster_whisper import WhisperModel


def main():
    if len(sys.argv) < 2:
        print("ASR_JSON {\"ok\": false, \"error\": \"no input file\"}")
        return 1
    path = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else None
    model_size = sys.argv[3] if len(sys.argv) > 3 else "small"
    started = time.time()
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            path,
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        payload = {
            "ok": True,
            "text": text,
            "language": getattr(info, "language", "") or "",
            "duration": getattr(info, "duration", 0) or 0,
            "seconds": round(time.time() - started, 2),
        }
    except Exception as e:  # честный отказ, без выдуманной расшифровки
        payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print("ASR_JSON " + json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
