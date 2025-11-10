# from scripts.subtitles import generate_subtitles
from scripts.text_to_speech import generate_audio_from_json
from scripts.get_info import get_speach
from scripts.get_images import get_images
from scripts.build_video import build_video
from scripts.subtitles import generate_subtitles
from scripts.burner import burn_subtitles
from scripts.mix_audio import run


print("📝 Generating audio...")
generate_audio_from_json()

print("📝 Mixing Audios...")
mixed_path = run()

print("📝 Building video...")
build_video()

print("📝 Generating subtitle...")
ass_file = generate_subtitles()

print("📝 Burning subtitle...")
burn_subtitles("assets/video/output.mp4", ass_file, "assets/video/output_sub.mp4")
