import json

# Open and load the JSON file
with open("assets/info/story_image_prompts.json", "r") as file:
    data = json.load(file)

# Print the data


print(data['image_prompts'][0])

# for i, prompt in enumerate(data["image_prompts"], start=1):
#     print(f"Prompt {i}: {prompt}\n")
