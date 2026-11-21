import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PILOT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "pilot_100.jsonl"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "annotation_prompt.md"
GUIDELINES_PATH = PROJECT_ROOT / "prompts" / "annotation_guidelines.md"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "pilot" / "annotations_100_posts.json"

load_dotenv(PROJECT_ROOT / ".env")

CHECKPOINT_VERSION = 1
EXPECTED_PILOT_POSTS = 100
MAX_ATTEMPTS = 8
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 120.0
TPM_LIMIT = 8000
TPM_SAFETY_FACTOR = 0.85
MAX_PACING_SECONDS = 75.0

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

CHECKPOINT_FIELDS = {
    "checkpoint_version",
    "created_at",
    "updated_at",
    "model",
    "configured_model",
    "pilot_file",
    "prompt_file",
    "guidelines_file",
    "prompt_sha256",
    "guidelines_sha256",
    "num_posts_expected",
    "num_annotations_expected",
    "posts",
    "summary",
}

POST_ENTRY_FIELDS = {
    "pilot_id",
    "sample_id",
    "post_text",
    "num_candidate_aspects",
    "num_annotations_returned",
    "annotations",
    "validation",
}

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
RETRYABLE_ERROR_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "ServiceUnavailableError",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def relative_path(path):
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def load_pilot_records():
    if not PILOT_PATH.is_file():
        raise SystemExit(f"Pilot file not found: {PILOT_PATH}")
    records = []
    with PILOT_PATH.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise SystemExit(f"Blank line at pilot JSONL line {line_number}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise SystemExit(
                    f"Invalid JSON at pilot JSONL line {line_number}: {error}"
                )
            if not isinstance(record, dict):
                raise SystemExit(
                    f"Pilot record at line {line_number} is not a JSON object"
                )
            for key in ("pilot_id", "sample_id", "text", "aspects"):
                if key not in record:
                    raise SystemExit(
                        f"Pilot record at line {line_number} is missing field: {key}"
                    )
            if not isinstance(record["pilot_id"], str):
                raise SystemExit(
                    f"Pilot record at line {line_number} has a non-string pilot_id"
                )
            if isinstance(record["sample_id"], bool) or not isinstance(
                record["sample_id"], int
            ):
                raise SystemExit(
                    f"Pilot record at line {line_number} has a non-integer sample_id"
                )
            if not isinstance(record["text"], str):
                raise SystemExit(
                    f"Pilot record at line {line_number} has a non-string text"
                )
            aspects = record["aspects"]
            if not isinstance(aspects, list) or not aspects:
                raise SystemExit(
                    f"Pilot record at line {line_number} has no candidate aspects"
                )
            for index, aspect in enumerate(aspects):
                if not isinstance(aspect, dict) or not isinstance(
                    aspect.get("aspect"), str
                ):
                    raise SystemExit(
                        f"Pilot record at line {line_number} has a malformed aspect at index {index}"
                    )
            if "num_aspects" in record and record["num_aspects"] != len(aspects):
                raise SystemExit(
                    f"Pilot record at line {line_number} has num_aspects={record['num_aspects']!r} "
                    f"but {len(aspects)} aspects"
                )
            records.append(record)

    if len(records) != EXPECTED_PILOT_POSTS:
        raise SystemExit(
            f"Expected {EXPECTED_PILOT_POSTS} pilot records, found {len(records)}"
        )

    pilot_ids = [record["pilot_id"] for record in records]
    sample_ids = [record["sample_id"] for record in records]
    if len(set(pilot_ids)) != len(pilot_ids):
        raise SystemExit("Pilot record pilot IDs are not distinct")
    if len(set(sample_ids)) != len(sample_ids):
        raise SystemExit("Pilot record sample IDs are not distinct")
    return records


def load_instructions():
    for path in (PROMPT_PATH, GUIDELINES_PATH):
        if not path.is_file():
            raise SystemExit(f"Instruction file not found: {path}")
    prompt_raw = PROMPT_PATH.read_text(encoding="utf-8")
    guidelines_raw = GUIDELINES_PATH.read_text(encoding="utf-8")
    if not prompt_raw.strip():
        raise SystemExit(f"Instruction file is empty: {PROMPT_PATH}")
    if not guidelines_raw.strip():
        raise SystemExit(f"Instruction file is empty: {GUIDELINES_PATH}")
    system_prompt = prompt_raw.rstrip()
    return system_prompt, sha256_text(prompt_raw), sha256_text(guidelines_raw)


def build_messages(record, system_prompt):
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
        {"role": "system", "content": system_prompt},
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


def is_retryable(error):
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    if status in RETRYABLE_STATUS_CODES:
        return True
    return type(error).__name__ in RETRYABLE_ERROR_NAMES


def retry_after_seconds(error):
    headers = getattr(getattr(error, "response", None), "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def request_completion(client, model, messages, pilot_id):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.chat.completions.create(
                model=model,
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
                max_completion_tokens=2000,
            )
        except Exception as error:
            if not is_retryable(error) or attempt == MAX_ATTEMPTS:
                raise
            delay = min(
                MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS ** attempt
            ) + random.uniform(0.0, 0.5)
            status = getattr(error, "status_code", None)
            if status is None:
                status = getattr(getattr(error, "response", None), "status_code", None)
            if status == 429:
                delay = max(delay, 30.0)
            requested_delay = retry_after_seconds(error)
            if requested_delay is not None:
                delay = min(MAX_BACKOFF_SECONDS, max(delay, requested_delay))
            print(
                f"Temporary API failure for {pilot_id} "
                f"(attempt {attempt}/{MAX_ATTEMPTS}): {type(error).__name__}. "
                f"Retrying in {delay:.1f}s."
            )
            time.sleep(delay)


def pace_after_response(response):
    usage = getattr(response, "usage", None)
    total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int) or total_tokens <= 0:
        total_tokens = 5000
    interval = 60.0 * total_tokens / (TPM_LIMIT * TPM_SAFETY_FACTOR)
    interval = min(MAX_PACING_SECONDS, max(0.0, interval))
    if interval > 0:
        time.sleep(interval)


def atomic_write(document):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = OUTPUT_PATH.with_name(OUTPUT_PATH.name + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, OUTPUT_PATH)


def build_checkpoint(records, total_expected, configured_model, prompt_hash, guidelines_hash):
    now = utc_now()
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "created_at": now,
        "updated_at": now,
        "model": configured_model,
        "configured_model": configured_model,
        "pilot_file": relative_path(PILOT_PATH),
        "prompt_file": relative_path(PROMPT_PATH),
        "guidelines_file": relative_path(GUIDELINES_PATH),
        "prompt_sha256": prompt_hash,
        "guidelines_sha256": guidelines_hash,
        "num_posts_expected": len(records),
        "num_annotations_expected": total_expected,
        "posts": [],
        "summary": {},
    }


def build_post_entry(record, annotations):
    return {
        "pilot_id": record["pilot_id"],
        "sample_id": record["sample_id"],
        "post_text": record["text"],
        "num_candidate_aspects": len(record["aspects"]),
        "num_annotations_returned": len(annotations),
        "annotations": annotations,
        "validation": {"valid": True, "errors": []},
    }


def build_summary(records, completed, total_expected):
    annotations = []
    for record in records:
        entry = completed.get(record["pilot_id"])
        if entry is not None:
            annotations.extend(entry["annotations"])
    distribution = {label: 0 for label in sorted(ALLOWED_LABELS)}
    for annotation in annotations:
        distribution[annotation["label"]] += 1
    num_completed = len(completed)
    complete = (
        num_completed == len(records)
        and len(annotations) == total_expected
    )
    valid = all(
        entry.get("validation", {}).get("valid") is True
        for entry in completed.values()
    )
    if complete:
        valid = valid and len(annotations) == total_expected
    return {
        "num_posts_expected": len(records),
        "num_posts_completed": num_completed,
        "num_posts_remaining": len(records) - num_completed,
        "num_annotations_expected": total_expected,
        "num_annotations_returned": len(annotations),
        "label_distribution": distribution,
        "complete": complete,
        "validation": {"valid": valid, "errors": []},
    }


def refresh_checkpoint(checkpoint, records, completed, total_expected):
    checkpoint["posts"] = [
        completed[record["pilot_id"]]
        for record in records
        if record["pilot_id"] in completed
    ]
    checkpoint["updated_at"] = utc_now()
    checkpoint["summary"] = build_summary(records, completed, total_expected)


def load_checkpoint():
    if not OUTPUT_PATH.is_file():
        return None
    try:
        with OUTPUT_PATH.open("r", encoding="utf-8") as handle:
            checkpoint = json.load(handle)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"Checkpoint is not valid JSON: {OUTPUT_PATH}: {error}. "
            "Refusing to overwrite it."
        )
    if not isinstance(checkpoint, dict):
        raise SystemExit(
            f"Checkpoint is not a JSON object: {OUTPUT_PATH}. Refusing to overwrite it."
        )
    return checkpoint


def validate_checkpoint_entry(entry, record):
    errors = []
    if not isinstance(entry, dict):
        return ["Post entry is not a JSON object"]
    keys = set(entry.keys())
    required = set(POST_ENTRY_FIELDS)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        errors.append(f"Post entry is missing fields: {missing}")
    if extra:
        errors.append(f"Post entry has extra fields: {extra}")

    if entry.get("pilot_id") != record["pilot_id"]:
        errors.append(
            f"Post entry pilot_id expected {record['pilot_id']!r}, got {entry.get('pilot_id')!r}"
        )
    if entry.get("sample_id") != record["sample_id"]:
        errors.append(
            f"Post entry sample_id expected {record['sample_id']}, got {entry.get('sample_id')!r}"
        )
    if entry.get("post_text") != record["text"]:
        errors.append("Post entry post_text does not match the pilot record")
    if entry.get("num_candidate_aspects") != len(record["aspects"]):
        errors.append(
            f"Post entry num_candidate_aspects expected {len(record['aspects'])}, "
            f"got {entry.get('num_candidate_aspects')!r}"
        )

    annotations = entry.get("annotations")
    if not isinstance(annotations, list):
        errors.append("Post entry annotations must be a JSON array")
        annotations = []
    else:
        if entry.get("num_annotations_returned") != len(annotations):
            errors.append(
                f"Post entry num_annotations_returned expected {len(annotations)}, "
                f"got {entry.get('num_annotations_returned')!r}"
            )
        response_errors, _ = validate_post_response(
            {"annotations": annotations}, record
        )
        errors.extend(response_errors)

    validation = entry.get("validation")
    if not isinstance(validation, dict):
        errors.append("Post entry validation must be a JSON object")
    else:
        if validation.get("valid") is not True:
            errors.append("Post entry validation.valid is not true")
        if validation.get("errors"):
            errors.append(
                f"Post entry validation.errors is not empty: {validation.get('errors')!r}"
            )

    return errors


def validate_checkpoint(
    checkpoint,
    records,
    prompt_hash,
    guidelines_hash,
    configured_model,
):
    errors = []
    missing = sorted(CHECKPOINT_FIELDS - set(checkpoint.keys()))
    if missing:
        errors.append(f"Checkpoint is missing fields: {missing}")
    if checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION:
        errors.append(
            f"Checkpoint version expected {CHECKPOINT_VERSION}, "
            f"got {checkpoint.get('checkpoint_version')!r}"
        )
    if checkpoint.get("prompt_sha256") != prompt_hash:
        errors.append(
            "Checkpoint prompt_sha256 does not match the current prompt file; "
            "refusing to mix annotation policies"
        )
    if checkpoint.get("guidelines_sha256") != guidelines_hash:
        errors.append(
            "Checkpoint guidelines_sha256 does not match the current guidelines file; "
            "refusing to mix annotation policies"
        )
    if configured_model is not None and checkpoint.get("configured_model") != configured_model:
        errors.append(
            f"Checkpoint configured_model expected {configured_model!r}, "
            f"got {checkpoint.get('configured_model')!r}"
        )

    total_expected = sum(len(record["aspects"]) for record in records)
    if checkpoint.get("num_posts_expected") != len(records):
        errors.append(
            f"Checkpoint num_posts_expected expected {len(records)}, "
            f"got {checkpoint.get('num_posts_expected')!r}"
        )
    if checkpoint.get("num_annotations_expected") != total_expected:
        errors.append(
            f"Checkpoint num_annotations_expected expected {total_expected}, "
            f"got {checkpoint.get('num_annotations_expected')!r}"
        )

    posts = checkpoint.get("posts")
    if not isinstance(posts, list):
        errors.append("Checkpoint posts must be a JSON array")
        return errors, {}

    records_by_id = {record["pilot_id"]: record for record in records}
    completed = {}
    for index, entry in enumerate(posts):
        if not isinstance(entry, dict):
            errors.append(f"Checkpoint post entry {index} is not a JSON object")
            continue
        pilot_id = entry.get("pilot_id")
        if pilot_id not in records_by_id:
            errors.append(
                f"Checkpoint post entry {index} has unknown pilot_id {pilot_id!r}"
            )
            continue
        if pilot_id in completed:
            errors.append(f"Checkpoint contains duplicate pilot_id {pilot_id!r}")
            continue
        entry_errors = validate_checkpoint_entry(entry, records_by_id[pilot_id])
        if entry_errors:
            errors.extend(f"{pilot_id}: {error}" for error in entry_errors)
            continue
        completed[pilot_id] = entry

    return errors, completed


def print_summary(summary, model, output_path):
    print(f"Model: {model}")
    print(
        f"Posts completed: {summary['num_posts_completed']}/"
        f"{summary['num_posts_expected']}"
    )
    print(f"Posts remaining: {summary['num_posts_remaining']}")
    print(f"Annotations expected: {summary['num_annotations_expected']}")
    print(f"Annotations returned: {summary['num_annotations_returned']}")
    print("Label distribution:")
    for label in sorted(ALLOWED_LABELS):
        print(f"  {label}: {summary['label_distribution'].get(label, 0)}")
    print(f"Checkpoint complete: {'YES' if summary['complete'] else 'NO'}")
    print(
        f"Validation: {'PASSED' if summary['validation']['valid'] else 'FAILED'}"
    )
    for error in summary["validation"]["errors"]:
        print(f"  - {error}")
    print(f"Output: {output_path}")


def validate_only():
    records = load_pilot_records()
    total_expected = sum(len(record["aspects"]) for record in records)
    _, prompt_hash, guidelines_hash = load_instructions()
    print(
        f"Input validation PASSED: {len(records)} posts, "
        f"{total_expected} candidate aspects."
    )
    print(f"Prompt SHA-256: {prompt_hash}")
    print(f"Guidelines SHA-256: {guidelines_hash}")

    checkpoint = load_checkpoint()
    if checkpoint is None:
        print(f"No checkpoint found at {OUTPUT_PATH}; input validation only.")
        return

    configured_model = os.getenv("GROQ_MODEL")
    errors, completed = validate_checkpoint(
        checkpoint,
        records,
        prompt_hash,
        guidelines_hash,
        configured_model,
    )
    summary = build_summary(records, completed, total_expected)
    print_summary(
        summary,
        checkpoint.get("model") or configured_model or "unknown",
        OUTPUT_PATH,
    )
    if errors:
        print("Checkpoint validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    print("Checkpoint validation PASSED.")


def run_annotation():
    api_key = os.getenv("GROQ_API_KEY")
    configured_model = os.getenv("GROQ_MODEL")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is missing from .env")
    if not configured_model:
        raise SystemExit("GROQ_MODEL is missing from .env")

    records = load_pilot_records()
    total_expected = sum(len(record["aspects"]) for record in records)
    system_prompt, prompt_hash, guidelines_hash = load_instructions()
    print(f"Loaded prompt (system instruction): {PROMPT_PATH}")
    print(f"Loaded guidelines (reference/hash): {GUIDELINES_PATH}")
    print(f"Model: {configured_model}")
    print(f"Output: {OUTPUT_PATH}")
    print(
        f"Pilot input: {len(records)} posts, {total_expected} candidate aspects."
    )

    checkpoint = load_checkpoint()
    completed = {}
    if checkpoint is None:
        checkpoint = build_checkpoint(
            records,
            total_expected,
            configured_model,
            prompt_hash,
            guidelines_hash,
        )
    else:
        errors, completed = validate_checkpoint(
            checkpoint,
            records,
            prompt_hash,
            guidelines_hash,
            configured_model,
        )
        if errors:
            print("Existing checkpoint validation FAILED; refusing to continue:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        print(
            f"Resuming from checkpoint: {len(completed)}/{len(records)} posts complete, "
            f"{total_expected - sum(len(entry['annotations']) for entry in completed.values())} "
            "annotations remaining."
        )

    if len(completed) == len(records):
        refresh_checkpoint(checkpoint, records, completed, total_expected)
        print("All 100 posts are already annotated; no API calls were made.")
        print_summary(
            checkpoint["summary"],
            checkpoint.get("model") or configured_model,
            OUTPUT_PATH,
        )
        if not checkpoint["summary"]["validation"]["valid"]:
            sys.exit(1)
        return

    client = Groq(api_key=api_key)
    for record in records:
        pilot_id = record["pilot_id"]
        if pilot_id in completed:
            continue

        print(
            f"Annotating {pilot_id} / sample {record['sample_id']} "
            f"({len(record['aspects'])} aspects)..."
        )
        messages = build_messages(record, system_prompt)
        try:
            response = request_completion(
                client, configured_model, messages, pilot_id
            )
            actual_model = getattr(response, "model", None) or configured_model
            content = response.choices[0].message.content
        except Exception as error:
            print(
                f"API request failed for {pilot_id}: "
                f"{type(error).__name__}: {error}"
            )
            print(
                "No checkpoint update was made for this post. "
                "Previously completed posts remain saved."
            )
            sys.exit(1)

        if checkpoint.get("model") in (None, configured_model):
            checkpoint["model"] = actual_model
        elif actual_model != checkpoint["model"]:
            print(
                f"Model changed during the run: checkpoint has "
                f"{checkpoint['model']!r}, response reports {actual_model!r}. "
                "No checkpoint update was made for this post."
            )
            sys.exit(1)

        if not content:
            print(
                f"Model returned empty content for {pilot_id}. "
                "No checkpoint update was made."
            )
            sys.exit(1)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            print(f"Invalid JSON for {pilot_id}: {error}")
            print(
                "The response was not repaired. No checkpoint update was made."
            )
            sys.exit(1)

        errors, annotations = validate_post_response(parsed, record)
        if errors:
            print(f"Validation FAILED for {pilot_id}; no checkpoint update was made:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)

        completed[pilot_id] = build_post_entry(record, annotations)
        refresh_checkpoint(checkpoint, records, completed, total_expected)
        try:
            atomic_write(checkpoint)
        except OSError as error:
            print(f"Could not save checkpoint: {type(error).__name__}: {error}")
            sys.exit(1)

        summary = checkpoint["summary"]
        print(
            f"  {pilot_id}: {len(annotations)}/{len(record['aspects'])} annotations, "
            f"validation PASSED, checkpoint "
            f"{summary['num_posts_completed']}/{len(records)} posts."
        )
        if len(completed) < len(records):
            pace_after_response(response)

    refresh_checkpoint(checkpoint, records, completed, total_expected)
    print("Annotation run complete.")
    print_summary(
        checkpoint["summary"],
        checkpoint.get("model") or configured_model,
        OUTPUT_PATH,
    )
    if not checkpoint["summary"]["validation"]["valid"]:
        sys.exit(1)


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--validate-only":
            validate_only()
        else:
            raise SystemExit(
                f"Unknown argument: {sys.argv[1]!r}. "
                "Use --validate-only to validate inputs and any existing checkpoint."
            )
        return
    run_annotation()


if __name__ == "__main__":
    main()
