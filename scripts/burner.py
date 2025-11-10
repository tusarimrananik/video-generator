from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

def _filter_safe_path(p: Path) -> str:
    """
    Make a path safe for ffmpeg's subtitles filter on Windows.
    On Windows, escape the drive colon (e.g., C:\ -> C\\:).
    """
    s = p.resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", s):
        s = s[0] + r"\:" + s[2:]
    return s

def burn_subtitles(
    video_in: str | Path,
    ass_path: str | Path,
    out_path: str | Path,
    *,
    vcodec: str = "libx264",
    acodec: str = "aac",
    preset: str = "medium",
    crf: int = 18,
    pix_fmt: str = "yuv420p",
    overwrite: bool = True,
    loglevel: str = "error",
    fonts_dir: Optional[str | Path] = None,  # set if your ASS references custom fonts
) -> Path:
    """
    Burn a word-level ASS (with inline styling) into a video using ffmpeg.
    This does not modify the subtitle file; it just burns it in.
    """
    video_in = Path(video_in).resolve()
    ass_path = Path(ass_path).resolve()
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_in.exists():
        raise FileNotFoundError(f"Video not found: {video_in}")
    if not ass_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {ass_path}")

    vf_parts = [f"filename='{_filter_safe_path(ass_path)}'"]
    if fonts_dir:
        vf_parts.append(f"fontsdir='{_filter_safe_path(Path(fonts_dir))}'")
    vf = "subtitles=" + ":".join(vf_parts)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y" if overwrite else "-n",
        "-loglevel", loglevel,
        "-i", str(video_in),
        "-vf", vf,                 # burn the ASS
        "-c:v", vcodec,
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", pix_fmt,
        "-c:a", acodec,
        str(out_path),
    ]
    print("🔧 Running ffmpeg to burn subtitles...")
    subprocess.run(cmd, check=True)
    print(f"✅ Subtitled video saved: {out_path.resolve()}")
    return out_path
