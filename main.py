# ALL IMPORTS
import re
# import os

# import stat
# from typing import Union
# from pathlib import Path

# from scripts.build_video import render_to_file, SlideshowParams
from pathlib import Path

# from scripts.get_images import download_images
from scripts.text_to_speech import load_tts, generate_audio

from scripts.get_info import get_speach

# from pathlib import Path
# from scripts.subtitles import generate_subtitles
# from scripts.burner import burn_subtitles


# HELPER FOR DELETING FILES
# def delete_files_only(folder_path: Union[str, os.PathLike]) -> int:
#     folder_path = os.fspath(folder_path)
#     if not os.path.exists(folder_path):
#         raise FileNotFoundError(f"{folder_path!r} does not exist")
#     if not os.path.isdir(folder_path):
#         raise NotADirectoryError(f"{folder_path!r} is not a directory")
#     deleted = 0
#     for root, dirs, files in os.walk(folder_path):
#         for name in files:
#             fp = os.path.join(root, name)
#             try:
#                 try:
#                     st_mode = os.stat(fp).st_mode
#                     os.chmod(fp, st_mode | stat.S_IWUSR)
#                 except Exception:
#                     pass

#                 os.remove(fp)
#                 deleted += 1
#             except FileNotFoundError:
#                 continue
#     return deleted


# DOWNLOAD AND SAVE IMAGES
# delete_files_only("assets/images")
# download_images("tech", per_page=10)


# # MOTIVATIONAL SCRIPTS

speech_text = get_speach("Overcoming challenges and achieving success")

file_path = Path("assets/text/speech.txt")
file_path.parent.mkdir(parents=True, exist_ok=True)  # creates assets/text if missing

file_path.write_text(speech_text, encoding="utf-8")

speech = file_path.read_text(encoding="utf-8")

sentences = re.split(r"(?<=[.!?]) +", speech)


# # TEXT TO SPEACH
# delete_files_only("assets/audio/generated")
speaker_wav = "assets/audio/reference/Brain.wav"
tts = load_tts()
generate_audio(
    tts,
    sentences,
    speaker_wav,
    output_dir="assets/audio/generated",
    output_file="assets/audio/generated/output.wav",
)
# delete_files_only("assets/audio/generated/chunks")


# # BUILD VIDEO
# delete_files_only("assets/video")


# def get_images_from_folder(folder: str | Path):
#     folder = Path(folder)
#     if not folder.exists():
#         raise FileNotFoundError(f"Image folder not found: {folder}")
#     image_paths = sorted(
#         [p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}],
#         key=lambda p: (
#             p.stem.isdigit(),
#             int(p.stem) if p.stem.isdigit() else p.stem.lower(),
#             p.name.lower(),
#         ),
#     )
#     if not image_paths:
#         raise FileNotFoundError(f"No images found in {folder}")
#     return image_paths


# images = get_images_from_folder("assets/images")
# params = SlideshowParams(fps=10, target_w=1080, target_h=1920)
# render_to_file(
#     image_paths=images,
#     audio="assets/audio/generated/output.wav",
#     out_path="assets/video/output.mp4",
#     params=params,
# )


# # GENERATE SUBTITLE
# audio_file = "assets/audio/generated/output.wav"
# ass_output = "assets/subtitles/output.ass"
# generate_subtitles(
#     audio_path=audio_file,
#     ass_out_path=ass_output,
#     text_to_align=speech,
# )

# burn_subtitles(
#     video_in="assets/video/output.mp4",
#     ass_path="assets/subtitles/output.ass",
#     out_path="assets/video/output_subtitled.mp4",
# )
