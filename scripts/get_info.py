from dotenv import load_dotenv
import openai
import os
import json

load_dotenv()

openai.api_key = os.getenv("GPT4_API_KEY")


def get_speach(prompt: str, save_path: str = "assets/info/story_image_prompts.json"):
    """
    Generates a short (max 6-line) story plus 5 image prompts as JSON
    and saves it to `save_path`. Prints the saved path instead of returning the JSON.
    """
    try:
        response = openai.completions.create(
            model="gpt-4o-mini",
            prompt=f"""You are a creative writer and visual imagination expert.
Using the theme: {prompt}, write a short story with a MAXIMUM of 6 lines.
Each line must be a full, meaningful sentence (English only, family-friendly).
Then create exactly 5 self-contained image prompts that illustrate the key moments
of the story. Each image prompt should describe the scene vividly, including
subjects, environment, mood, lighting, composition, and style.

Return ONLY valid JSON (no markdown, no commentary) using this format:
{{
  "story": ["line 1", "line 2", "line 3", "line 4", "line 5", "line 6"],
  "image_prompts": [
    "prompt 1",
    "prompt 2",
    "prompt 3",
    "prompt 4",
    "prompt 5"
  ]
}}
Use double quotes for everything and ensure valid JSON only.""",
            max_tokens=700,  # sufficient for 6 lines + 5 prompts
            temperature=0.6,  # balanced creativity and structure
        )

        text = response.choices[0].text.strip()

        # Try to parse JSON; if model adds extra text, trim to the outermost braces.
        data = None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass

        # Ensure directory exists and save
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            if data is not None:
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                # Fallback: write the raw text if JSON parsing failed
                f.write(text)

        print(f"✅ JSON saved to {save_path}")
        # No JSON return; function ends here.
    except Exception as e:
        print(f"❌ Error generating story/image data: {e}")
