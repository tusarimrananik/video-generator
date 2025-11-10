from __future__ import annotations
from pathlib import Path


def generate_subtitles() -> Path:
    import os
    import re
    import json
    from typing import List
    from pydub import AudioSegment
    import whisperx  # type: ignore

    # --- Prevent Windows crash ---
    os.environ["TRANSFORMERS_NO_TORCHVISION"] = "1"
    os.environ["TORCHVISION_DISABLE_NMS_EXPORT"] = "1"

    # --- Default Paths ---
    models_root = Path("models").resolve()
    json_path = Path("assets/info/story_image_prompts.json")
    audio_path = Path("assets/audio/generated/output.wav")
    ass_out_path = Path("assets/subtitles/output.ass")

    # --- Load story text ---
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    story_lines = data.get("story", [])
    if not story_lines or not isinstance(story_lines, list):
        raise ValueError(f"'story' key missing or empty in {json_path}")
    text_to_align = " ".join(line.strip() for line in story_lines if line.strip())

    # --- Check model checkpoint ---
    ckpt = (
        models_root
        / "hub"
        / "checkpoints"
        / "wav2vec2_fairseq_base_ls960_asr_ls960.pth"
    )
    if not ckpt.exists():
        raise FileNotFoundError(f"Missing alignment checkpoint: {ckpt}")

    os.environ["TORCH_HOME"] = str(models_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    # --- Subtitle appearance defaults (visuals only) ---
    playres_w = 1080
    playres_h = 1920
    font = "DejaVu Sans Mono"
    fontsize = 54
    primary_color = "&H00FFFFFF"  # white (unused by inline, kept for completeness)
    outline_color = "&H00000000"  # black (unused by inline, kept for completeness)
    alignment = 5  # 5 = top-center (use 2 for bottom-center)
    margin_l = 60
    margin_r = 60
    margin_v = 40

    # Inline overrides (match your sample exactly)
    inline_fs = 84
    inline_prefix = (
        r"{\b1\fs" + str(inline_fs) + r"\1c&HFFFFFF&\3c&H000000&\bord4\shad0}"
    )

    # --- Prepare audio and segments ---
    ass_out_path.parent.mkdir(parents=True, exist_ok=True)
    duration_s = AudioSegment.from_file(audio_path).duration_seconds
    segments = [{"start": 0.0, "end": duration_s, "text": text_to_align}]

    # --- Align text with WhisperX (UNTOUCHED loading behavior) ---
    align_model, metadata = whisperx.load_align_model(language_code="en", device="cpu")
    aligned = whisperx.align(segments, align_model, metadata, str(audio_path), "cpu")

    # --- Helpers ---
    def fmt_time(t: float) -> str:
        if t < 0:
            t = 0.0
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        cs = int(round((t - int(t)) * 100))
        if cs >= 100:
            cs = 0
            s += 1
            if s >= 60:
                s = 0
                m += 1
                if m >= 60:
                    m = 0
                    h += 1
        return f"{h}:{m:02}:{s:02}.{cs:02}"

    def esc(text: str) -> str:
        return (
            text.replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", r"\N")
        )

    # Remove ONLY trailing punctuation (keep internal apostrophes etc.)
    # You mentioned "(, . ! etc)" — here’s a broad but end-only set.
    trailing_punct_re = re.compile(r"""[)\]\}\.,!?:;'"“”‘’\-–—…]+$""")

    def strip_trailing_punct(token: str) -> str:
        return trailing_punct_re.sub("", token)

    # --- ASS file header (single style 'HL'; actual look via inline overrides) ---
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"
        f"PlayResX:{playres_w}\n"
        f"PlayResY:{playres_h}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Keep a simple HL style; inline tags will override size/color/bold/outline.
        f"Style: HL,{font},{fontsize},{primary_color},&H000000FF,{outline_color},&H00000000,"
        f"0,0,0,0,100,100,0,0,1,3,0,{alignment},{margin_l},{margin_r},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines: List[str] = [header]

    # --- WORD-LEVEL ONLY: one Dialogue per word, with inline styling and no trailing punctuation ---
    for seg in aligned.get("segments", []):
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue
            raw = str(w.get("word", "")).strip()
            if not raw:
                continue
            token = strip_trailing_punct(raw).upper()
            if not token:
                # token was only punctuation at the end; skip
                continue
            lines.append(
                f"Dialogue: 1,{fmt_time(float(w['start']))},{fmt_time(float(w['end']))},HL,,"
                f"{margin_l},{margin_r},{margin_v},,"
                f"{inline_prefix}{esc(token)}\n"
            )

    ass_out_path.write_text("".join(lines), encoding="utf-8")
    print(
        f"✅ Word-level subtitles written (no trailing punctuation): {ass_out_path.resolve()}"
    )
    return ass_out_path
