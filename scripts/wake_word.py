#!/usr/bin/env python3
"""Wake word listener for Zeus desktop.

Continuously listens to the microphone for "zeus" or "hey zeus".
When detected, prints a JSON line to stdout:

    {"detected": true, "phrase": "hey zeus", "full_text": "hey zeus"}

Status/error lines are also JSON:

    {"status": "listening"}
    {"error": "microphone not available"}

Reads optional JSON commands from stdin:

    {"action": "stop"}    — shut down cleanly
"""

import json
import sys
import threading

try:
    import speech_recognition as sr
except ImportError:
    print(json.dumps({"error": "speech_recognition not installed. Run: pip install SpeechRecognition PyAudio"}))
    sys.stdout.flush()
    sys.exit(1)


def emit(obj):
    """Print a JSON event to stdout and flush immediately."""
    print(json.dumps(obj), flush=True)


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

        try:
            # Use Google's free speech recognition for wake word detection
            text = recognizer.recognize_google(audio).lower().strip()
        except sr.UnknownValueError:
            # No speech detected — keep listening
            continue
        except sr.RequestError as e:
            emit({"error": f"recognition service error: {e}"})
            stop_event.wait(2.0)
            continue
        except Exception as e:
            emit({"error": f"recognition error: {e}"})
            continue

        # Check for wake word
        wake_words = ["zeus", "hey zeus", "hey zero"]
        matched = next((w for w in wake_words if w in text), None)

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
