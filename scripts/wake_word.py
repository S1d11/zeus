#!/usr/bin/env python3
"""Wake word listener for Hermes desktop.

Continuously listens to the microphone for "hermes" or "hey hermes".
When detected, prints a JSON line to stdout:

    {"detected": true, "phrase": "hey hermes", "full_text": "hey hermes"}

Status/error lines are also JSON:

    {"status": "listening"}
    {"error": "microphone not available"}

Reads optional JSON commands from stdin:

    {"action": "stop"}    — shut down cleanly

Recognition strategy (tries each in order until one works):
  1. PocketSphinx offline (keyword spotting — lightweight, no internet)
  2. Google free speech-to-text (requires internet, rate-limited)
  3. Vosk offline (if installed — lightweight, accurate, no internet)

The wake word "hermes" is phonetically similar to several common words
("use", "loose", "juice", "deuce"), so we match a broad set of
near-homophones to avoid false negatives.
"""

import json
import sys
import threading
import time

try:
    import speech_recognition as sr
except ImportError:
    print(json.dumps({"error": "speech_recognition not installed. Run: pip install SpeechRecognition PyAudio"}))
    sys.stdout.flush()
    sys.exit(1)


def emit(obj):
    """Print a JSON event to stdout and flush immediately."""
    print(json.dumps(obj), flush=True)


# Wake words and common misrecognitions of "hermes" / "hey hermes".
# Google's free STT frequently transcribes "hermes" as these near-homophones.
WAKE_WORDS = [
    "hermes",
    "hey hermes",
    "hey zero",
    # Common misrecognitions of "hermes" alone:
    "use",
    "loose",
    "juice",
    "deuce",
    "goose",
    "moose",
    # Common misrecognitions of "hey hermes":
    "hey use",
    "hey loose",
    "hey juice",
    "a hermes",
    "the hermes",
]

# Words that look like wake words but are NOT — filter out false positives.
# e.g. "use" alone is too common, so we only accept it if preceded by "hey"
# or if the full text is very short (just the one word).
SINGLE_WORD_ACCEPT = {"hermes", "loose", "juice", "deuce", "goose", "moose"}
# "use" alone is too common in normal speech — only accept with "hey"
HEADED_WORDS = {"use", "deuce"}


def matches_wake_word(text: str) -> str | None:
    """Return the matched wake word if text contains one, else None.

    Filters out false positives where a single common word like "use"
    appears alone without "hey" prefix.
    """
    text = text.lower().strip()
    if not text:
        return None

    # Check multi-word phrases first (higher confidence)
    for word in WAKE_WORDS:
        if " " in word and word in text:
            return word

    # Single-word matches: filter false positives
    words = text.split()
    for word in WAKE_WORDS:
        if " " not in word and word in words:
            # Words like "use" are too common in normal speech — only accept
            # if preceded by "hey" (already caught by multi-word match above)
            if word in HEADED_WORDS:
                continue
            if word not in SINGLE_WORD_ACCEPT and len(words) == 1:
                # Unknown single word — skip to avoid false positives
                continue
            # Only accept single-word matches when the utterance is short
            # (1-2 words). In a long sentence, "loose" or "juice" are likely
            # not wake words.
            if len(words) > 2:
                continue
            return word

    return None


def _try_sphinx(recognizer, audio):
    """Attempt offline recognition using PocketSphinx (bundled with SpeechRecognition).

    Returns the recognized text (lowercased) or None if unavailable or no speech.
    """
    try:
        text = recognizer.recognize_sphinx(audio).lower().strip()
        return text if text else None
    except sr.UnknownValueError:
        return None
    except LookupError:
        # PocketSphinx not installed
        return None
    except Exception:
        return None


def _try_vosk(recognizer, audio):
    """Attempt offline recognition using Vosk (if installed).

    Returns the recognized text (lowercased) or None.
    """
    try:
        text = recognizer.recognize_vosk(audio).lower().strip()
        # Vosk returns JSON like {"text": "hey hermes"}
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                text = parsed.get("text", "").lower().strip()
            except (json.JSONDecodeError, AttributeError):
                return None
        return text if text else None
    except sr.UnknownValueError:
        return None
    except (LookupError, AttributeError):
        # Vosk not installed or not configured
        return None
    except Exception:
        return None


def _try_google(recognizer, audio):
    """Attempt Google's free speech recognition (requires internet).

    Returns the recognized text (lowercased) or None.
    """
    try:
        text = recognizer.recognize_google(audio).lower().strip()
        return text if text else None
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        # Google API unavailable (offline or rate-limited)
        return None
    except Exception:
        return None


def recognize(recognizer, audio):
    """Try each recognition backend in order. Returns (text, backend) or (None, None)."""
    # Try PocketSphinx first — it's offline, fast, and doesn't rate-limit
    text = _try_sphinx(recognizer, audio)
    if text:
        return text, "sphinx"

    # Try Vosk — offline, more accurate than Sphinx if installed
    text = _try_vosk(recognizer, audio)
    if text:
        return text, "vosk"

    # Fall back to Google's free API (may rate-limit or fail offline)
    text = _try_google(recognizer, audio)
    if text:
        return text, "google"

    return None, None


def listen_loop(stop_event):
    """Continuously listen for the wake word until stop_event is set."""
    recognizer = sr.Recognizer()

    # Tuning: lower energy threshold for sensitivity, adjust dynamically
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    # Shorter pause threshold so we detect quickly
    recognizer.pause_threshold = 0.5
    # Phrase threshold — how long of a phrase to capture
    recognizer.phrase_threshold = 0.3

    try:
        mic = sr.Microphone()
    except Exception as e:
        emit({"error": f"microphone not available: {e}"})
        return

    # Calibrate for ambient noise once at startup
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
        emit({"status": "listening"})
    except Exception as e:
        emit({"error": f"calibration failed: {e}"})
        return

    consecutive_errors = 0
    last_backend = None

    while not stop_event.is_set():
        try:
            with mic as source:
                # Non-blocking listen with timeout so we can check stop_event
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=5)
        except sr.WaitTimeoutError:
            continue
        except Exception as e:
            emit({"error": f"listen error: {e}"})
            # Brief recovery pause before retrying
            stop_event.wait(0.5)
            continue

        text, backend = recognize(recognizer, audio)

        if text is None:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                emit({"error": "all recognition backends failing — check microphone and dependencies"})
                consecutive_errors = 0
                stop_event.wait(2.0)
            continue

        consecutive_errors = 0

        # Log backend changes for debugging
        if backend != last_backend:
            emit({"status": f"using {backend} recognition"})
            last_backend = backend

        # Check for wake word
        matched = matches_wake_word(text)

        if matched:
            emit({"detected": True, "phrase": matched, "full_text": text})
        # Otherwise keep listening


def read_stdin(stop_event):
    """Read JSON commands from stdin until stop or EOF."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cmd.get("action") == "stop":
            stop_event.set()
            return


def main():
    stop_event = threading.Event()

    # Start stdin reader in background thread
    stdin_thread = threading.Thread(target=read_stdin, args=(stop_event,), daemon=True)
    stdin_thread.start()

    # Run the listen loop in the main thread
    listen_loop(stop_event)

    # Clean exit
    stop_event.set()
    emit({"status": "stopped"})


if __name__ == "__main__":
    main()
