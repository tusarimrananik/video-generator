# scripts/text_to_speech.py
from TTS.api import TTS
from pydub import AudioSegment
import os, time, json, glob

# -------------------------------
# 🔧 Paths you can change if needed
# -------------------------------
MODEL_PATH = r"models/tts_models--multilingual--multi-dataset--xtts_v2"
JSON_PATH = r"assets/info/story_image_prompts.json"  # <- sentences come from here
SPEAKER_WAV = (
    r"assets/audio/reference/voice_sample.wav"  # <- put your reference voice here
)
OUTPUT_DIR = r"assets/audio/generated"
OUTPUT_FILE = r"assets/audio/generated/output.wav"
CHUNKS_DIR = os.path.join(OUTPUT_DIR, "chunks")


def load_tts(model_path=MODEL_PATH, gpu=False):
    """Load the XTTS v2 model."""
    print(f"⏳ Loading XTTS v2 model from: {model_path}")
    tts = TTS(
        model_path=model_path,
        config_path=os.path.join(model_path, "config.json"),
        gpu=gpu,
    )
    print("✅ Model loaded.\n")
    return tts


def load_sentences(json_path=JSON_PATH, key="story"):
    """Read sentences from JSON; default key = 'story'."""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON not found: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if key not in data or not isinstance(data[key], list):
        raise ValueError(f"Key '{key}' missing or not a list in {json_path}")

    sentences = [s.strip() for s in data[key] if isinstance(s, str) and s.strip()]
    if not sentences:
        raise ValueError(f"No sentences found under '{key}' in {json_path}")
    print(f"📝 Loaded {len(sentences)} sentences from {json_path}\n")
    return sentences


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)


def clean_chunks():
    # optional: wipe old chunk_*.wav so we don't accidentally merge leftovers
    for f in glob.glob(os.path.join(CHUNKS_DIR, "chunk_*.wav")):
        try:
            os.remove(f)
        except OSError:
            pass


def generate_audio_from_json():
    """Main worker: load model, read JSON, synthesize, and merge."""
    ensure_dirs()
    clean_chunks()

    if not os.path.exists(SPEAKER_WAV):
        raise FileNotFoundError(
            f"Speaker reference not found: {SPEAKER_WAV}\n"
            f"→ place a sample voice WAV there (16k/22k/44.1k ok)."
        )

    tts = load_tts(gpu=False)  # set True if you have a compatible GPU
    sentences = load_sentences(JSON_PATH, key="story")

    all_chunks = []
    for i, sentence in enumerate(sentences, 1):
        file_chunk = os.path.join(CHUNKS_DIR, f"chunk_{i}.wav")
        print(f"🔊 [{i}/{len(sentences)}] {sentence}")
        start = time.time()
        tts.tts_to_file(
            text=sentence,
            speaker_wav=SPEAKER_WAV,
            language="en",
            file_path=file_chunk,
        )
        print(f"   ✅ done in {time.time() - start:.2f}s")
        all_chunks.append(AudioSegment.from_wav(file_chunk))

    if not all_chunks:
        raise RuntimeError("No chunks produced — check JSON content.")

    final_audio = sum(all_chunks)
    final_audio.export(OUTPUT_FILE, format="wav")
    clean_chunks()
    print(f"\n🎧 Final audio saved to: {OUTPUT_FILE}")
