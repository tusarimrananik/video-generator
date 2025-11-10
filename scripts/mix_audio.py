# scripts/mix_audio.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from moviepy import AudioFileClip, CompositeAudioClip, afx

# Optional loop FX (present in most installs). If unavailable, we fall back gracefully.
try:
    from moviepy.audio.fx.all import audio_loop  # v1/v2 compatible import path
except Exception:
    audio_loop = None

# ===== Defaults (edit as you like) =====
MAIN_PATH   = Path("assets/audio/generated/output.wav")   # primary/narration
BG_PATH     = Path("assets/audio/music/Observer.mp3")           # background music
OUT_PATH    = Path("assets/audio/generated/mix.wav")      # output mix

MAIN_VOLUME = 1.0    # 100%
BG_VOLUME   = 0.20   # 20%
TARGET      = "main" # "main" = match main length, "max" = longest
STRATEGY    = "cut"  # "cut" or "loop"
SAMPLE_RATE = 48000  # 48 kHz is video-friendly


def _apply_volume_v2(clip: AudioFileClip, factor: float):
    """
    MoviePy v2 way to set volume: apply audio effect via with_effects + afx.MultiplyVolume.
    This works on AudioClip and VideoClip audio alike.
    """
    return clip.with_effects([afx.MultiplyVolume(factor)])


def _apply_volume_compat(clip: AudioFileClip, factor: float):
    """
    Compatibility: prefer v2 effect; if someone runs v1 where effects aren't available the same way,
    try volumex if it exists.
    """
    try:
        return _apply_volume_v2(clip, factor)
    except Exception:
        if hasattr(clip, "volumex"):  # v1 dynamic method
            return clip.volumex(factor)
        raise


def mix_audio(
    main_path: Path,
    bg_path: Path,
    out_path: Path,
    main_volume: float = MAIN_VOLUME,
    bg_volume: float = BG_VOLUME,
    target: str = TARGET,
    strategy: str = STRATEGY,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    """
    Mix two audio files (main + background@bg_volume) and save to out_path.
    Returns the written file path.
    """
    if not main_path.exists():
        raise FileNotFoundError(f"Main audio not found: {main_path}")
    if not bg_path.exists():
        raise FileNotFoundError(f"Background audio not found: {bg_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    main_clip = bg_clip = mixed = None
    try:
        main_clip = _apply_volume_compat(AudioFileClip(str(main_path)), main_volume)
        bg_clip   = _apply_volume_compat(AudioFileClip(str(bg_path)),   bg_volume)

        # Decide target duration
        if target == "max":
            final_duration = max(float(main_clip.duration), float(bg_clip.duration))
        else:
            final_duration = float(main_clip.duration)

        # Fit durations
        main_clip = main_clip.with_duration(final_duration)

        if strategy == "loop" and bg_clip.duration < final_duration and audio_loop:
            bg_clip = audio_loop(bg_clip, duration=final_duration)
        else:
            bg_clip = bg_clip.with_duration(final_duration)

        # Mix and export
        mixed = CompositeAudioClip([bg_clip, main_clip]).with_duration(final_duration)
        mixed.write_audiofile(str(out_path), fps=sample_rate)
        return out_path

    finally:
        for clip in (mixed, main_clip, bg_clip):
            try:
                if clip is not None:
                    clip.close()
            except Exception:
                pass


def run() -> Path:
    """Run with defaults; returns output file path."""
    return mix_audio(
        main_path=MAIN_PATH,
        bg_path=BG_PATH,
        out_path=OUT_PATH,
        main_volume=MAIN_VOLUME,
        bg_volume=BG_VOLUME,
        target=TARGET,
        strategy=STRATEGY,
        sample_rate=SAMPLE_RATE,
    )


if __name__ == "__main__":
    out = run()
    print(str(out))
