
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

# Locate project root and load API configuration
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL")

if not api_key or not model:
    raise ValueError("Check GROQ_API_KEY and GROQ_MODEL in .env")

client = Groq(api_key=api_key)

# Define the exact annotation record structure
annotation_schema = {
    "type": "object",
    "properties": {
        "pilot_id": {"type": "string"},
        "sample_id": {"type": "integer"},
        "aspect_index": {"type": "integer"},
        "aspect": {"type": "string"},
        "label": {
            "type": "string",
            "enum": ["explicit", "implicit", "not_identifiable"]
        },
        "evidence": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        }
    },
    "required": [
        "pilot_id",
        "sample_id",
        "aspect_index",
        "aspect",
        "label",
        "evidence",
        "reason",
        "confidence"
    ],
    "additionalProperties": False
}

# Use synthetic test data, not an actual pilot record
messages = [
    {
        "role": "system",
        "content": (
            "You are a careful text-only aspect explicitness annotator. "
            "Classify the supplied candidate aspect using only the supplied text. "
            "Use explicit, implicit, or not_identifiable. "
            "If explicit, evidence must be an exact substring of the text. "
            "Return exactly one annotation record."
        )
    },
    {
        "role": "user",
        "content": (
            'TEST ONLY\n'
            'pilot_id: TEST-001\n'
            'sample_id: 0\n'
            'aspect_index: 0\n'
            'post_text: "The battery life is excellent."\n'
            'candidate_aspect: "battery life"\n'
            'Return the annotation using the required schema.'
        )
    }
]

# Request strict JSON Schema output
response = client.chat.completions.create(
    model=model,
    messages=messages,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "ox_mabsr_annotation_record",
            "strict": True,
            "schema": annotation_schema
        }
    },
    temperature=0,
    max_completion_tokens=500
)

# Parse and display the response
content = response.choices[0].message.content

if not content:
    raise ValueError("The model returned an empty response.")

result = json.loads(content)

print("\nSTRUCTURED OUTPUT RECEIVED")
print(json.dumps(result, indent=4, ensure_ascii=False))

# Basic local checks
assert result["label"] in {
    "explicit", "implicit", "not_identifiable"
}
assert 0 <= result["confidence"] <= 1
assert result["pilot_id"] == "TEST-001"
assert result["aspect"] == "battery life"
assert result["evidence"] in ("", "battery life")

print("\nSUCCESS: Structured JSON output received and basic checks passed.")
