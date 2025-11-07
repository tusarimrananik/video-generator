# scripts/build_video.py
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union, List, Optional

# MoviePy v2 import style (no "moviepy.editor")
from moviepy import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    vfx,
    VideoClip,
)

PathLike = Union[str, Path]

# ===== Defaults =====
IMAGE_DIR = Path("assets/images")
AUDIO_PATH = Path("assets/audio/generated/output.wav")
OUTPUT_DIR = Path("assets/video")
OUTPUT_PATH = OUTPUT_DIR / "output.mp4"


# ==================== CONFIG ====================
@dataclass
class SlideshowParams:
    target_w: int = 1080
    target_h: int = 1920
    fps: int = 30                    # smoother for shorts
    min_per_image: float = 3.0
    whip_max: float = 0.45           # max crossfade duration cap

    # Look / motion
    contrast: float = 1.08
    zoom_start: float = 1.00
    zoom_end_even: float = 1.06
    zoom_end_odd: float = 1.08

    # Global fades
    global_fade_in_cap: float = 0.30
    global_fade_out_cap: float = 0.25
    global_fade_in_frac: float = 0.15
    global_fade_out_frac: float = 0.12

    # Robustness against edge artifacts / black bars
    overscan: float = 1.003          # ~0.3% overscale
    safety_min_body: float = 0.4     # min visible body per image (ex-fade)


# ==================== HELPERS ====================
def _collect_images(dir_path: PathLike) -> List[Path]:
    p = Path(dir_path)
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"Image directory not found: {dir_path}")
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    files = sorted([q for q in p.iterdir() if q.suffix.lower() in exts])
    if not files:
        raise ValueError(f"No images found in: {dir_path}")
    return files


def sample_evenly(seq: Sequence, k: int) -> List:
    n = len(seq)
    if n == 0:
        raise ValueError("No items to sample.")
    if k <= 1:
        return [seq[0]]
    idxs = [round(i * (n - 1) / (k - 1)) for i in range(k)]
    return [seq[i] for i in idxs]


def ease_in_out_cubic(p: float) -> float:
    p = max(0.0, min(1.0, p))
    if p < 0.5:
        return 4 * p * p * p
    return 1 - ((-2 * p + 2) ** 3) / 2


def quantize_time_to_frame(t: float, fps: float) -> float:
    frame = 1.0 / fps
    return round(t / frame) * frame


def safe_xfade(per_img: float, fps: float, whip_max: float) -> float:
    """Pick a smooth, frame-aligned crossfade duration."""
    proposed = min(whip_max, max(0.25, per_img * 0.22))
    min_body = max(0.4, 2.0 / fps)
    max_fade = max(0.0, per_img - min_body)
    proposed = min(proposed, max_fade)

    q = quantize_time_to_frame(proposed, fps)
    min_fade = 2.0 / fps
    if q < min_fade and proposed >= min_fade:
        q = min_fade
    return max(0.0, q)


# ==================== CLIP BUILDER ====================
def _make_clip(
    img_path: PathLike,
    duration: float,
    idx: int,
    p: SlideshowParams,
) -> VideoClip:
    """Create a center-anchored Ken Burns zoom clip from one image."""
    base0 = ImageClip(str(img_path)).with_duration(duration)

    # "Cover" fit + small overscan so the image always exceeds the canvas
    cover_scale = max(p.target_w / base0.w, p.target_h / base0.h) * p.overscan
    base = base0.resized(cover_scale)  # v2: resized()

    # Subtle contrast pop (v2: with_effects + class-based fx)
    base = base.with_effects([
        vfx.LumContrast(lum=0, contrast=p.contrast, contrast_threshold=128)
    ])

    def z_func(t: float) -> float:
        prog = t / max(duration, 1e-6)
        e = ease_in_out_cubic(prog)
        z_end = p.zoom_end_even if (idx % 2 == 0) else p.zoom_end_odd
        return p.zoom_start + (z_end - p.zoom_start) * e

    # IMPORTANT: integer (w,h) with ceil avoids rounding underfill/black bars
    def size_func(t: float):
        z = z_func(t)
        w = int(math.ceil(base.w * z))
        h = int(math.ceil(base.h * z))
        return (w, h)

    zoomed = base.resized(size_func).with_position("center")  # v2: resized()

    comp = CompositeVideoClip([zoomed], size=(p.target_w, p.target_h))
    comp = comp.with_duration(duration)
    return comp


# ==================== CORE BUILDER ====================
def _build_video_core(
    image_paths: Sequence[PathLike],
    audio_clip: AudioFileClip,
    params: Optional[SlideshowParams] = None,
) -> VideoClip:
    if not image_paths:
        raise ValueError("image_paths is empty.")

    p = params or SlideshowParams()
    total_audio = max(0.01, float(audio_clip.duration))

    # Decide how many images we can fit at minimum duration each
    max_images = max(1, int(total_audio // p.min_per_image))
    if len(image_paths) > max_images:
        image_paths = sample_evenly(image_paths, max_images)

    n = len(image_paths)

    if n == 1:
        per_img_final = quantize_time_to_frame(total_audio, p.fps)
        clip = _make_clip(image_paths[0], per_img_final, 0, p)
        video = concatenate_videoclips([clip], method="compose")

        gi = min(p.global_fade_in_cap, per_img_final * p.global_fade_in_frac)
        go = min(p.global_fade_out_cap, per_img_final * p.global_fade_out_frac)
        video = video.with_effects([vfx.FadeIn(gi), vfx.FadeOut(go)])

        total_quant = quantize_time_to_frame(total_audio, p.fps)
        return video.with_audio(audio_clip).with_duration(total_quant)

    # Multi-image slideshow
    per_img_naive = total_audio / n
    xfade = safe_xfade(per_img_naive, p.fps, p.whip_max)

    # In overlap concat, each interior clip contributes (per_img_final - xfade)
    per_img_final = (total_audio + (n - 1) * xfade) / n
    per_img_final = quantize_time_to_frame(per_img_final, p.fps)
    xfade = quantize_time_to_frame(xfade, p.fps)

    min_body = max(p.safety_min_body, 2.0 / p.fps)
    if per_img_final <= xfade + min_body:
        # dial back crossfade until body is safe
        xfade_frames = int(max(0, round(xfade * p.fps)))
        while per_img_final <= (xfade_frames / p.fps) + min_body and xfade_frames > 0:
            xfade_frames -= 1
        xfade = xfade_frames / p.fps

    base_clips: List[VideoClip] = [
        _make_clip(path, per_img_final, i, p) for i, path in enumerate(image_paths)
    ]

    if xfade > 0:
        # Apply CrossFadeIn to all but the first clip (v2: with_effects)
        clips = [base_clips[0]] + [
            c.with_effects([vfx.CrossFadeIn(xfade)]) for c in base_clips[1:]
        ]
        video = concatenate_videoclips(clips, method="compose", padding=-xfade)
    else:
        video = concatenate_videoclips(base_clips, method="compose")

    gi = min(p.global_fade_in_cap, per_img_final * p.global_fade_in_frac)
    go = min(p.global_fade_out_cap, per_img_final * p.global_fade_out_frac)
    video = video.with_effects([vfx.FadeIn(gi), vfx.FadeOut(go)])

    total_quant = quantize_time_to_frame(total_audio, p.fps)
    return video.with_audio(audio_clip).with_duration(total_quant)


# ==================== PUBLIC API (writes file) ====================
def build_video() -> str:
    """
    Build the slideshow from defaults and write to assets/video/output.mp4.
    Returns the output path as a string.
    """
    images = _collect_images(IMAGE_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    audio_clip = AudioFileClip(str(AUDIO_PATH))
    try:
        video = _build_video_core(images, audio_clip, SlideshowParams())
        try:
            video.write_videofile(
                str(OUTPUT_PATH),
                fps=SlideshowParams().fps,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                threads=4,
                bitrate="8000k",
                ffmpeg_params=["-pix_fmt", "yuv420p"],  # safest for phone players
            )
        finally:
            try:
                video.close()
            except Exception:
                pass
    finally:
        audio_clip.close()

    return str(OUTPUT_PATH)


if __name__ == "__main__":
    print(build_video())
