from TTS.api import TTS
from pydub import AudioSegment
import os, time

# -------------------------------
# 🔹 XTTS v2 model folder
# -------------------------------
MODEL_PATH = r"models/tts_models--multilingual--multi-dataset--xtts_v2"


def load_tts(model_path=MODEL_PATH, gpu=False):
    """Load the XTTS v2 model."""
    print(f"⏳ Loading XTTS v2 model from: {model_path}")
    tts = TTS(
        model_path=model_path,
        config_path=os.path.join(model_path, "config.json"),
        gpu=gpu,
    )
    print("✅ Model loaded successfully.\n")
    return tts


def generate_audio(
    tts,
    sentences,
    speaker_wav,
    output_dir="assets/audio/generated",
    output_file="assets/audio/generated/output.wav",
):
    """Generate speech from sentences, merge them, and save final audio."""
    os.makedirs(output_dir, exist_ok=True)
    all_chunks = []

    for i, sentence in enumerate(sentences, 1):
        file_chunk = os.path.join(output_dir, "chunks", f"chunk_{i}.wav")
        print(f"🔊 [{i}/{len(sentences)}] Generating: {sentence}")
        start = time.time()

        tts.tts_to_file(
            text=sentence, speaker_wav=speaker_wav, language="en", file_path=file_chunk
        )

        print(f"   ✅ Done in {time.time() - start:.2f}s")
        all_chunks.append(AudioSegment.from_wav(file_chunk))

    # Merge chunks into one file
    final_audio = sum(all_chunks)
    final_audio.export(output_file, format="wav")
