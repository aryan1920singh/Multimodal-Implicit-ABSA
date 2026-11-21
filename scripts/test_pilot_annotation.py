import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PILOT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "pilot_100.jsonl"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "annotation_prompt.md"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "test_annotation_single_post.json"

load_dotenv(PROJECT_ROOT / ".env")

ALLOWED_LABELS = {"explicit", "implicit", "not_identifiable"}
FIELDS = [
    "pilot_id",
    "sample_id",
    "aspect_index",
    "aspect",
    "label",
    "evidence",
    "reason",
    "confidence",
]

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "pilot_id": {"type": "string"},
        "sample_id": {"type": "integer"},
        "aspect_index": {"type": "integer"},
        "aspect": {"type": "string"},
        "label": {"type": "string", "enum": sorted(ALLOWED_LABELS)},
        "evidence": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": FIELDS,
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "annotations": {
            "type": "array",
            "items": ITEM_SCHEMA,
        }
    },
    "required": ["annotations"],
    "additionalProperties": False,
}


def load_first_record():
    if not PILOT_PATH.is_file():
        raise SystemExit(f"Pilot file not found: {PILOT_PATH}")
    with PILOT_PATH.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
    if not first_line.strip():
        raise SystemExit("Pilot file is empty")
    record = json.loads(first_line)
    for key in ("pilot_id", "sample_id", "text", "aspects"):
        if key not in record:
            raise SystemExit(f"First pilot record is missing field: {key}")
    aspects = record["aspects"]
    if not isinstance(aspects, list) or not aspects:
        raise SystemExit("First pilot record has no candidate aspects")
    for index, item in enumerate(aspects):
        if not isinstance(item, dict) or not isinstance(item.get("aspect"), str):
            raise SystemExit(f"Candidate aspect at index {index} is malformed")
    return record


def build_messages(record):
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    lines = [
        f"pilot_id: {record['pilot_id']}",
        f"sample_id: {record['sample_id']}",
        f"post_text: {record['text']}",
        "candidate_aspects:",
    ]
    for index, item in enumerate(record["aspects"]):
        lines.append(f"  {index}: {item['aspect']}")
    lines.append("")
    lines.append(
        "Return one JSON object matching the supplied schema. "
        f"The 'annotations' array must contain exactly {len(record['aspects'])} objects, "
        "one per candidate aspect, in the same order. "
        "Each annotation object must use exactly the eight fields from the prompt."
    )
    return [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": "\n".join(lines)},
    ]


def validate_annotation(annotation, record, index):
    errors = []
    if not isinstance(annotation, dict):
        return [f"annotation[{index}] is not a JSON object"]

    keys = set(annotation.keys())
    required = set(FIELDS)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        errors.append(f"annotation[{index}] is missing fields: {missing}")
    if extra:
        errors.append(f"annotation[{index}] has extra fields: {extra}")

    pilot_id = annotation.get("pilot_id")
    if not isinstance(pilot_id, str) or pilot_id != record["pilot_id"]:
        errors.append(
            f"annotation[{index}].pilot_id expected {record['pilot_id']!r}, got {pilot_id!r}"
        )

    sample_id = annotation.get("sample_id")
    if isinstance(sample_id, bool) or not isinstance(sample_id, int) or sample_id != record["sample_id"]:
        errors.append(
            f"annotation[{index}].sample_id expected {record['sample_id']}, got {sample_id!r}"
        )

    aspect_index = annotation.get("aspect_index")
    if isinstance(aspect_index, bool) or not isinstance(aspect_index, int) or aspect_index != index:
        errors.append(
            f"annotation[{index}].aspect_index expected {index}, got {aspect_index!r}"
        )

    expected_aspect = record["aspects"][index]["aspect"]
    aspect = annotation.get("aspect")
    if not isinstance(aspect, str) or aspect != expected_aspect:
        errors.append(
            f"annotation[{index}].aspect expected {expected_aspect!r}, got {aspect!r}"
        )

    label = annotation.get("label")
    if not isinstance(label, str) or label not in ALLOWED_LABELS:
        errors.append(
            f"annotation[{index}].label must be one of {sorted(ALLOWED_LABELS)}, got {label!r}"
        )

    evidence = annotation.get("evidence")
    if not isinstance(evidence, str):
        errors.append(f"annotation[{index}].evidence must be a string")
    else:
        if evidence and evidence not in record["text"]:
            errors.append(
                f"annotation[{index}].evidence is not an exact substring of post_text"
            )
        if label in {"explicit", "implicit"} and evidence == "":
            errors.append(
                f"annotation[{index}].evidence must be non-empty for label {label!r}"
            )

    reason = annotation.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"annotation[{index}].reason must be a non-empty string")

    confidence = annotation.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append(f"annotation[{index}].confidence must be numeric")
    elif not 0 <= confidence <= 1:
        errors.append(
            f"annotation[{index}].confidence must be between 0 and 1, got {confidence!r}"
        )

    return errors


def validate_response(parsed, record):
    errors = []
    if not isinstance(parsed, dict):
        return ["Response is not a JSON object"], []
    if set(parsed.keys()) != {"annotations"}:
        errors.append(
            f"Response must contain only the 'annotations' field, got {sorted(parsed.keys())}"
        )
    annotations = parsed.get("annotations")
    if not isinstance(annotations, list):
        errors.append("'annotations' must be a JSON array")
        return errors, []
    if len(annotations) != len(record["aspects"]):
        errors.append(
            f"Expected {len(record['aspects'])} annotations, got {len(annotations)}"
        )
    for index, annotation in enumerate(annotations):
        if index >= len(record["aspects"]):
            errors.append(f"annotation[{index}] has no matching candidate aspect")
            continue
        errors.extend(validate_annotation(annotation, record, index))
    return errors, annotations


def write_result(document):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main():
    api_key = os.getenv("GROQ_API_KEY")
    configured_model = os.getenv("GROQ_MODEL")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is missing from .env")
    if not configured_model:
        raise SystemExit("GROQ_MODEL is missing from .env")

    record = load_first_record()
    messages = build_messages(record)
    client = Groq(api_key=api_key)

    result_document = {
        "model": None,
        "configured_model": configured_model,
        "pilot_id": record["pilot_id"],
        "sample_id": record["sample_id"],
        "post_text": record["text"],
        "num_candidate_aspects": len(record["aspects"]),
        "num_annotations_returned": 0,
        "annotations": [],
        "validation": {"valid": False, "errors": []},
    }

    try:
        response = client.chat.completions.create(
            model=configured_model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ox_mabsr_post_annotations",
                    "strict": True,
                    "schema": RESPONSE_SCHEMA,
                },
            },
            temperature=0,
            max_completion_tokens=4000,
        )
        result_document["model"] = getattr(response, "model", None) or configured_model
        content = response.choices[0].message.content
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        result_document["validation"]["errors"] = [message]
        write_result(result_document)
        print(f"Configured model: {configured_model}")
        print(f"API request failed: {message}")
        print(f"Result saved to: {OUTPUT_PATH}")
        sys.exit(1)

    if not content:
        result_document["validation"]["errors"] = ["The model returned an empty response"]
        write_result(result_document)
        print(f"Model: {result_document['model']}")
        print("Validation FAILED: the model returned an empty response")
        print(f"Result saved to: {OUTPUT_PATH}")
        sys.exit(1)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        result_document["validation"]["errors"] = [f"Invalid JSON: {error}"]
        write_result(result_document)
        print(f"Model: {result_document['model']}")
        print(f"Validation FAILED: invalid JSON: {error}")
        print(f"Result saved to: {OUTPUT_PATH}")
        sys.exit(1)

    errors, annotations = validate_response(parsed, record)
    result_document["annotations"] = annotations
    result_document["num_annotations_returned"] = len(annotations)
    result_document["validation"] = {"valid": not errors, "errors": errors}
    write_result(result_document)

    print(f"Model: {result_document['model']}")
    print(f"Configured model: {configured_model}")
    print(f"Pilot ID: {record['pilot_id']}")
    print(f"Sample ID: {record['sample_id']}")
    print(f"Candidate aspects: {len(record['aspects'])}")
    print(f"Annotations returned: {len(annotations)}")
    print("Annotation results:")
    print(json.dumps(annotations, indent=2, ensure_ascii=True))
    print(f"Validation: {'PASSED' if not errors else 'FAILED'}")
    for error in errors:
        print(f"  - {error}")
    print(f"Result saved to: {OUTPUT_PATH}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
