
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

# Find the project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(PROJECT_ROOT / ".env")

# Read the API key and model name
api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL")

# Check whether the API key exists
if not api_key:
    raise ValueError("GROQ_API_KEY is missing from .env")

if not model:
    raise ValueError("GROQ_MODEL is missing from .env")

# Create Groq client
client = Groq(api_key=api_key)

# Send a simple test request
response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "user",
            "content": "Reply with exactly this text: GROQ CONNECTION SUCCESSFUL"
        }
    ],
    temperature=0,
    max_completion_tokens=100
)

# Display the response
print("Model:", response.model)
print("Response:", response.choices[0].message.content)
print("API connection successful!")
