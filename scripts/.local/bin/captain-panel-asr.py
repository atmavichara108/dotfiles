#!/usr/bin/env python3
"""captain-panel-asr — оркестратор локальной транскрипции медиа пульта.

Медиа → ffmpeg → wav 16k mono → faster-whisper (venv) → ASR_JSON.
Секретов не читает, токенов не требует, текст наружу отдаёт одной JSON-строкой.
"""
import json
import os
import subprocess
import sys
import tempfile

VENV_PY = os.path.expanduser("~/.local/share/pipx/venvs/faster-whisper/bin/python")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "captain-panel-asr-worker.py")
PROXY = {
    "HTTP_PROXY": "http://127.0.0.1:10809",
    "HTTPS_PROXY": "http://127.0.0.1:10809",
}


def env_for_asr():
    env = os.environ.copy()
    env.pop("ALL_PROXY", None)
    env.pop("all_proxy", None)
    env.update(PROXY)
    env["HF_HUB_OFFLINE"] = "1"
    return env


def asr_json(payload):
    print("ASR_JSON " + json.dumps(payload, ensure_ascii=False))


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print("использование: captain-panel-asr.py ФАЙЛ [ЯЗЫК]")
        return 0
    src = args[0]
    language = args[1] if len(args) > 1 else None
    if not os.path.exists(src):
        asr_json({"ok": False, "error": "media file missing"})
        return 1
    if not os.path.exists(WORKER) or not os.path.exists(VENV_PY):
        asr_json({"ok": False, "error": "asr runtime unavailable"})
        return 1

    fd, wav = tempfile.mkstemp(prefix="captain-panel-", suffix=".wav")
    os.close(fd)
    try:
        ff = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
             "-f", "wav", wav],
            capture_output=True, text=True, timeout=600)
        if ff.returncode != 0:
            asr_json({"ok": False, "error": "ffmpeg failed"})
            return 1
        run = subprocess.run(
            [VENV_PY, WORKER, wav, language or "", "small"],
            capture_output=True, text=True, timeout=900, env=env_for_asr())
        line = ""
        for row in run.stdout.splitlines():
            if row.startswith("ASR_JSON "):
                line = row
                break
        if not line:
            asr_json({"ok": False, "error": "asr worker did not respond"})
            return 1
        payload = json.loads(line[len("ASR_JSON "):])
        payload["source"] = os.path.basename(src)
        asr_json(payload)
        return 0 if payload.get("ok") else 1
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
