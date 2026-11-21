import ast
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "ox_mabsr"
ENEM_TRAIN = RAW_DIR / "data" / "enem" / "train.txt"
IMG_TXT_DIR = RAW_DIR / "img_txt"
OUTPUT_DIR = BASE_DIR / "outputs" / "pilot"
JSONL_PATH = OUTPUT_DIR / "pilot_100.jsonl"
CSV_PATH = OUTPUT_DIR / "pilot_100.csv"
MANIFEST_PATH = OUTPUT_DIR / "pilot_manifest.json"

SEED = 42
PILOT_SIZE = 100
SCHEMA_VERSION = "pilot-v1"
SELECTION_METHOD = "sha256(seed:sample_id) ascending, take first N, then sort by numeric sample_id"


class PreparationError(Exception):
    pass


def fail(message):
    raise PreparationError(message)


def relative(path):
    return path.relative_to(BASE_DIR).as_posix()


def validate_aspects(parsed):
    if not isinstance(parsed, list):
        fail(f"annotation is {type(parsed).__name__}, expected list")
    if not parsed:
        fail("annotation contains no aspects")

    aspects = []
    for index, item in enumerate(parsed, 1):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            fail(f"aspect #{index} is not a 2-item tuple/list")
        aspect, labels = item
        if not isinstance(aspect, str) or not aspect.strip():
            fail(f"aspect #{index} has an invalid name")
        if not isinstance(labels, (list, tuple)) or not labels:
            fail(f"aspect {aspect!r} has no emotion labels")
        clean_labels = []
        for label in labels:
            if not isinstance(label, str) or not label.strip():
                fail(f"aspect {aspect!r} has an invalid emotion label")
            clean_labels.append(label)
        aspects.append({"aspect": aspect, "emotion_labels": clean_labels})
    return aspects


def load_enem_train():
    if not ENEM_TRAIN.is_file():
        fail(f"missing annotation file: {relative(ENEM_TRAIN)}")

    annotations = {}
    issues = {}
    seen_ids = set()
    duplicate_ids = []

    with ENEM_TRAIN.open("r", encoding="utf-8-sig", newline="") as handle:
        for lineno, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            sample_id, separator, payload = line.partition("\t")
            if not separator:
                fail(f"corrupt line {lineno} in {relative(ENEM_TRAIN)}: missing tab separator")
            if not sample_id.isdigit():
                fail(
                    f"corrupt line {lineno} in {relative(ENEM_TRAIN)}: "
                    f"non-numeric sample id {sample_id!r}"
                )
            sample_id = int(sample_id)
            if sample_id in seen_ids:
                duplicate_ids.append(sample_id)
                continue
            seen_ids.add(sample_id)
            try:
                parsed = ast.literal_eval(payload)
            except (ValueError, SyntaxError, MemoryError, RecursionError) as error:
                issues[sample_id] = (lineno, f"literal_eval failed: {error}")
                continue
            try:
                annotations[sample_id] = validate_aspects(parsed)
            except PreparationError as error:
                issues[sample_id] = (lineno, str(error))

    if duplicate_ids:
        fail(f"duplicate sample ids in {relative(ENEM_TRAIN)}: {sorted(set(duplicate_ids))[:10]}")
    if not seen_ids:
        fail(f"no annotations parsed from {relative(ENEM_TRAIN)}")
    return annotations, issues, seen_ids


def selection_rank(sample_id):
    return hashlib.sha256(f"{SEED}:{sample_id}".encode("utf-8")).hexdigest()


def select_ids(cohort_ids):
    if len(cohort_ids) < PILOT_SIZE:
        fail(f"cohort has {len(cohort_ids)} samples, need {PILOT_SIZE}")
    ranked = sorted(cohort_ids, key=selection_rank)
    return sorted(ranked[:PILOT_SIZE])


def load_text(sample_id):
    path = IMG_TXT_DIR / f"{sample_id}.txt"
    if not path.is_file():
        fail(f"missing text file for sample {sample_id}: {relative(path)}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw = handle.read()
    text = raw.rstrip("\r\n")
    if not text.strip():
        fail(f"empty text for sample {sample_id}: {relative(path)}")
    return path, text


def build_records(annotations, issues, selected_ids):
    records = []
    for pilot_index, sample_id in enumerate(selected_ids, 1):
        if sample_id in issues:
            lineno, reason = issues[sample_id]
            fail(
                f"selected sample {sample_id} is malformed "
                f"(line {lineno} of {relative(ENEM_TRAIN)}): {reason}"
            )
        text_path, text = load_text(sample_id)
        aspects = annotations[sample_id]
        records.append(
            {
                "pilot_id": f"P{pilot_index:03d}",
                "sample_id": sample_id,
                "split": "train",
                "text": text,
                "aspects": aspects,
                "num_aspects": len(aspects),
                "source": {
                    "text_file": relative(text_path),
                    "annotation_file": relative(ENEM_TRAIN),
                    "selection_seed": SEED,
                    "schema_version": SCHEMA_VERSION,
                },
            }
        )
    return records


def quality_report(records, cohort_size, issues):
    aspect_counts = [record["num_aspects"] for record in records]
    distribution = Counter(aspect_counts)
    duplicate_label_groups = 0
    total_labels = 0
    hashtag_aspects = 0
    for record in records:
        for aspect in record["aspects"]:
            labels = aspect["emotion_labels"]
            total_labels += len(labels)
            if len(labels) != len(set(labels)):
                duplicate_label_groups += 1
            if aspect["aspect"].startswith("#"):
                hashtag_aspects += 1
    return {
        "cohort_size": cohort_size,
        "selected_count": len(records),
        "duplicate_source_ids": 0,
        "malformed_source_lines": len(issues),
        "malformed_source_records": [
            {"line": lineno, "sample_id": sample_id, "reason": reason}
            for sample_id, (lineno, reason) in sorted(issues.items())
        ],
        "malformed_source_ids_excluded_from_output": sorted(issues),
        "malformed_selected_records": 0,
        "missing_text_files": 0,
        "empty_text_files": 0,
        "records_with_replacement_characters": sum(
            1 for record in records if "\ufffd" in record["text"]
        ),
        "replacement_character_count": sum(record["text"].count("\ufffd") for record in records),
        "records_with_non_ascii_text": sum(
            1 for record in records if any(ord(char) > 127 for char in record["text"])
        ),
        "total_aspects": sum(aspect_counts),
        "aspect_count_min": min(aspect_counts),
        "aspect_count_max": max(aspect_counts),
        "aspect_count_mean": round(sum(aspect_counts) / len(aspect_counts), 2),
        "aspect_count_distribution": {
            str(count): distribution[count] for count in sorted(distribution)
        },
        "aspects_with_duplicate_emotion_labels": duplicate_label_groups,
        "total_emotion_labels": total_labels,
        "aspects_starting_with_hashtag": hashtag_aspects,
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(records, path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_csv(records, path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["pilot_id", "sample_id", "split", "num_aspects", "text", "aspects"])
        for record in records:
            writer.writerow(
                [
                    record["pilot_id"],
                    record["sample_id"],
                    record["split"],
                    record["num_aspects"],
                    record["text"],
                    json.dumps(record["aspects"], ensure_ascii=False),
                ]
            )


def main():
    annotations, issues, cohort_ids = load_enem_train()
    selected_ids = select_ids(cohort_ids)
    records = build_records(annotations, issues, selected_ids)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(records, JSONL_PATH)
    write_csv(records, CSV_PATH)

    quality = quality_report(records, len(cohort_ids), issues)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "selection": {
            "seed": SEED,
            "method": SELECTION_METHOD,
            "pilot_size": PILOT_SIZE,
            "source_split": "train",
            "cohort_size": len(cohort_ids),
        },
        "selected_ids": selected_ids,
        "source_paths": {
            "annotation_file": relative(ENEM_TRAIN),
            "text_directory": relative(IMG_TXT_DIR),
        },
        "output_paths": {
            "jsonl": relative(JSONL_PATH),
            "csv": relative(CSV_PATH),
            "manifest": relative(MANIFEST_PATH),
        },
        "record_counts": {
            "cohort_annotated_ids": len(cohort_ids),
            "usable_annotations": len(annotations),
            "malformed_source_ids": len(issues),
            "selected_ids": len(selected_ids),
            "records_written": len(records),
        },
        "data_quality": quality,
        "checks": [
            "only enem/train.txt and img_txt/<ID>.txt were read",
            "validation, test, background, surface and thinking files were not opened",
            "all selected sample ids are numeric and unique in the source",
            "every selected sample id has a non-empty img_txt/<ID>.txt file",
            "annotations parsed with ast.literal_eval and shape-validated",
            "selected records abort on malformed annotation or missing text",
            "malformed source records outside the selection skipped and reported",
            "aspect names, emotion labels, casing, punctuation and duplicates preserved",
            "text read as UTF-8 with only trailing line terminators removed",
            "non-numeric filenames such as '(1)' copies are never matched",
            "original dataset files opened read-only",
        ],
        "reference_labels_only": True,
        "implicit_explicit_labels_generated": False,
        "output_sha256": {
            "jsonl": sha256_file(JSONL_PATH),
            "csv": sha256_file(CSV_PATH),
        },
    }
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"cohort annotated ids: {len(cohort_ids)}")
    print(f"usable annotations: {len(annotations)}")
    print(f"malformed source records skipped: {len(issues)}")
    for sample_id, (lineno, reason) in sorted(issues.items()):
        print(f"  skipped sample {sample_id} (line {lineno}): {reason}")
    print(f"selected ids: {len(selected_ids)}")
    print(f"records written: {len(records)}")
    print(f"total aspects: {quality['total_aspects']}")
    print(f"aspect count min/mean/max: {quality['aspect_count_min']}/{quality['aspect_count_mean']}/{quality['aspect_count_max']}")
    print(f"aspect count distribution: {quality['aspect_count_distribution']}")
    print(f"missing text files: {quality['missing_text_files']}")
    print(f"empty text files: {quality['empty_text_files']}")
    print(f"records with replacement chars: {quality['records_with_replacement_characters']}")
    print(f"output: {relative(JSONL_PATH)}")
    print(f"output: {relative(CSV_PATH)}")
    print(f"output: {relative(MANIFEST_PATH)}")


if __name__ == "__main__":
    try:
        main()
    except PreparationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
