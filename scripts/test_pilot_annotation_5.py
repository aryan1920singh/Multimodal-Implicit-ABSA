import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PILOT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "pilot_100.jsonl"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "annotation_prompt.md"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "test_annotation_5_posts.json"

load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "openai/gpt-oss-20b"
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


def load_pilot_records():
    if not PILOT_PATH.is_file():
        raise SystemExit(f"Pilot file not found: {PILOT_PATH}")
    records = []
    with PILOT_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise SystemExit(f"Blank line at pilot JSONL line {line_number}")
            record = json.loads(line)
            for key in ("pilot_id", "sample_id", "text", "aspects"):
                if key not in record:
                    raise SystemExit(
                        f"Pilot record at line {line_number} is missing field: {key}"
                    )
            aspects = record["aspects"]
            if not isinstance(aspects, list) or not aspects:
                raise SystemExit(
                    f"Pilot record at line {line_number} has no candidate aspects"
                )
            for index, aspect in enumerate(aspects):
                if not isinstance(aspect, dict) or not isinstance(aspect.get("aspect"), str):
                    raise SystemExit(
                        f"Pilot record at line {line_number} has a malformed aspect at index {index}"
                    )
            records.append(record)
    if not records:
        raise SystemExit("Pilot file is empty")
    return records


def select_records(records):
    if records[0]["pilot_id"] != "P001":
        raise SystemExit(
            f"Expected the first pilot record to be P001, got {records[0]['pilot_id']!r}"
        )
    selected = records[1:6]
    if len(selected) != 5:
        raise SystemExit(f"Expected 5 records after P001, found {len(selected)}")
    pilot_ids = [record["pilot_id"] for record in selected]
    sample_ids = [record["sample_id"] for record in selected]
    if len(set(pilot_ids)) != len(pilot_ids):
        raise SystemExit(f"Selected pilot IDs are not distinct: {pilot_ids}")
    if len(set(sample_ids)) != len(sample_ids):
        raise SystemExit(f"Selected sample IDs are not distinct: {sample_ids}")
    if "P001" in pilot_ids:
        raise SystemExit("P001 was selected; it must be excluded")
    if records[0]["sample_id"] in sample_ids:
        raise SystemExit("The P001 sample ID was selected; it must be excluded")
    return selected


def build_messages(record):
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    lines = [
        f"pilot_id: {record['pilot_id']}",
        f"sample_id: {record['sample_id']}",
        f"post_text: {record['text']}",
        "candidate_aspects:",
    ]
    for index, aspect in enumerate(record["aspects"]):
        lines.append(f"  {index}: {aspect['aspect']}")
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
        if isinstance(label, str) and label in {"explicit", "implicit"} and evidence == "":
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


def validate_post_response(parsed, record):
    errors = []
    if not isinstance(parsed, dict):
        return ["Response is not a JSON object"], []
    if set(parsed.keys()) != {"annotations"}:
        errors.append(
            f"Response must contain only the 'annotations' field, got {sorted(parsed.keys())}"
        )
    annotations = parsed.get("annotations")
    if not isinstance(annotations, list):
        return errors + ["'annotations' must be a JSON array"], []

    expected = len(record["aspects"])
    if len(annotations) != expected:
        errors.append(f"Expected {expected} annotations, got {len(annotations)}")

    occurrences = {}
    for annotation in annotations:
        if isinstance(annotation, dict):
            aspect_index = annotation.get("aspect_index")
            if isinstance(aspect_index, int) and not isinstance(aspect_index, bool):
                occurrences[aspect_index] = occurrences.get(aspect_index, 0) + 1
    for index in range(expected):
        count = occurrences.get(index, 0)
        if count != 1:
            errors.append(
                f"Candidate aspect index {index} ({record['aspects'][index]['aspect']!r}) "
                f"appears {count} times; expected exactly once"
            )

    for index, annotation in enumerate(annotations):
        if index >= expected:
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
    if configured_model != MODEL_NAME:
        raise SystemExit(
            f"GROQ_MODEL must be {MODEL_NAME!r}, got {configured_model!r}"
        )

    records = load_pilot_records()
    selected = select_records(records)
    client = Groq(api_key=api_key)

    total_expected = sum(len(record["aspects"]) for record in selected)
    result_document = {
        "model": None,
        "configured_model": configured_model,
        "num_posts": len(selected),
        "num_candidate_aspects": total_expected,
        "num_annotations_expected": total_expected,
        "num_annotations_returned": 0,
        "posts": [],
        "validation": {"valid": False, "errors": []},
    }
    overall_errors = []
    total_returned = 0

    for record in selected:
        post_entry = {
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
                messages=build_messages(record),
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
            actual_model = getattr(response, "model", None) or configured_model
            if result_document["model"] is None:
                result_document["model"] = actual_model
            content = response.choices[0].message.content
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            post_entry["validation"]["errors"] = [message]
            overall_errors.append(f"{record['pilot_id']}: {message}")
            result_document["posts"].append(post_entry)
            continue

        if not content:
            message = "The model returned an empty response"
            post_entry["validation"]["errors"] = [message]
            overall_errors.append(f"{record['pilot_id']}: {message}")
            result_document["posts"].append(post_entry)
            continue

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            message = f"Invalid JSON: {error}"
            post_entry["validation"]["errors"] = [message]
            overall_errors.append(f"{record['pilot_id']}: {message}")
            result_document["posts"].append(post_entry)
            continue

        errors, annotations = validate_post_response(parsed, record)
        post_entry["annotations"] = annotations
        post_entry["num_annotations_returned"] = len(annotations)
        post_entry["validation"] = {"valid": not errors, "errors": errors}
        total_returned += len(annotations)
        for error in errors:
            overall_errors.append(f"{record['pilot_id']}: {error}")
        result_document["posts"].append(post_entry)

    result_document["num_annotations_returned"] = total_returned
    result_document["validation"] = {
        "valid": (
            not overall_errors
            and total_returned == total_expected
            and all(post["validation"]["valid"] for post in result_document["posts"])
        ),
        "errors": overall_errors,
    }
    if result_document["model"] is None:
        result_document["model"] = configured_model
    write_result(result_document)

    pilot_ids = [post["pilot_id"] for post in result_document["posts"]]
    sample_ids = [post["sample_id"] for post in result_document["posts"]]

    print(f"Model: {result_document['model']}")
    print(f"Configured model: {configured_model}")
    print("Selected posts:")
    for post in result_document["posts"]:
        status = "PASSED" if post["validation"]["valid"] else "FAILED"
        print(
            f"  {post['pilot_id']} / sample {post['sample_id']}: "
            f"{post['num_candidate_aspects']} candidate aspects, "
            f"{post['num_annotations_returned']} annotations, {status}"
        )
    print(f"Selected pilot IDs: {pilot_ids}")
    print(f"Selected sample IDs: {sample_ids}")
    print(f"P001 excluded: {'P001' not in pilot_ids}")
    print(f"Selected records distinct: {len(set(pilot_ids)) == len(pilot_ids) == len(set(sample_ids)) == len(sample_ids)}")
    print(f"Total annotations expected: {total_expected}")
    print(f"Total annotations returned: {total_returned}")
    print(f"Validation: {'PASSED' if result_document['validation']['valid'] else 'FAILED'}")
    for error in overall_errors:
        print(f"  - {error}")
    print(f"Result saved to: {OUTPUT_PATH}")

    if not result_document["validation"]["valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
