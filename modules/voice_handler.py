"""
Module 7: Voice Handler (FREE)
- STT: local Whisper (openai-whisper) — runs on CPU, no API
- TTS: gTTS (Google Text-to-Speech, free, no key) → returns MP3 bytes
        fallback: pyttsx3 (offline)

Install: pip install openai-whisper gtts soundfile
"""

import os
import io
import tempfile
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
_whisper_model = None


# ── Whisper STT (local) ───────────────────────────────────────────────────────
def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print(f"Loading local Whisper '{WHISPER_MODEL_SIZE}' model (downloads ~140MB once)...")
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
        print("Whisper ready.")
    return _whisper_model


def transcribe_audio_bytes(
    audio_bytes: bytes,
    audio_format: str = "wav",
    language: Optional[str] = None,
) -> Tuple[str, float]:
    """
    Transcribe audio bytes using local Whisper. No API key needed.
    Returns (transcribed_text, confidence).
    """
    model = get_whisper_model()

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        options = {"language": language} if language else {}
        result = model.transcribe(tmp_path, **options)
        text = result["text"].strip()
        return text, (1.0 if text else 0.0)
    finally:
        os.unlink(tmp_path)


def transcribe_audio_file(file_path: str, language: Optional[str] = None) -> str:
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    ext = file_path.rsplit(".", 1)[-1].lower()
    text, _ = transcribe_audio_bytes(audio_bytes, audio_format=ext, language=language)
    return text


# ── TTS (gTTS — free Google TTS, returns MP3 bytes) ──────────────────────────
def text_to_speech(
    text: str,
    lang: str = "en",
    voice: str = "default",       # kept for API compatibility, unused
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Convert text to speech using gTTS (free, requires internet).
    Returns MP3 bytes that work directly with st.audio(..., format='audio/mp3').
    Falls back to pyttsx3 if gTTS is unavailable.

    Install: pip install gtts
    """
    # ── Primary: gTTS ────────────────────────────────────────────────────────
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        tts = gTTS(text=text[:500], lang=lang, slow=False)
        tts.write_to_fp(buf)
        audio_bytes = buf.getvalue()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

        return audio_bytes

    except ImportError:
        pass  # gTTS not installed, try fallback
    except Exception as e:
        print(f"gTTS failed ({e}), trying pyttsx3...")

    # ── Fallback: pyttsx3 (offline) ──────────────────────────────────────────
    try:
        import pyttsx3
        out = output_path or tempfile.mktemp(suffix=".wav")
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.save_to_file(text[:500], out)
        engine.runAndWait()
        with open(out, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"TTS unavailable: {e}")
        return None


def answer_for_voice(answer) -> str:
    """Convert a ChatAnswer object to clean TTS-friendly text."""
    text = answer.answer
    if getattr(answer, "caveat", None):
        text += f" Note: {answer.caveat}"
    sources = getattr(answer, "sources", [])
    if sources:
        text += f" This is based on {', '.join(sources[:2])}."
    return text


def is_valid_question(text: str, min_chars: int = 5) -> bool:
    if not text or len(text.strip()) < min_chars:
        return False
    noise = {"thank you", "thanks", "you", ".", "...", "okay", "um", "uh", ""}
    return text.strip().lower().rstrip(".") not in noise


if __name__ == "__main__":
    import sys
    print("Testing TTS...")
    audio = text_to_speech("The liability cap in this contract is fifty thousand dollars.")
    if audio:
        with open("/tmp/test_tts.mp3", "wb") as f:
            f.write(audio)
        print(f"TTS OK — {len(audio):,} bytes saved to /tmp/test_tts.mp3")
    else:
        print("TTS failed. Install gTTS: pip install gtts")

    if len(sys.argv) >= 2:
        print(f"\nTranscribing: {sys.argv[1]}")
        print(f"Result: {transcribe_audio_file(sys.argv[1])}")
