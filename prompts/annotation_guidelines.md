# OX-MABSR Annotation Guidelines

## Text-Only Aspect Explicitness Annotation

This document defines how to classify each candidate aspect against its original
social-media post using **text only**. It is written for annotators and for
anyone reviewing or validating annotations.

The task is to decide whether the post text itself makes the candidate aspect
identifiable, and to record the supporting evidence. The task is **not** to
judge sentiment, emotion, or image content.

> Important: this is the text-only phase of a multimodal project. It does not
> establish whether an aspect could be identified using the accompanying image.
> See Section 9.

---

## 1. Annotation unit

One annotation decision corresponds to **one post–aspect pair**.

- The pilot contains **100 posts** and **508 candidate aspects**.
- Each candidate aspect belongs to exactly one post.
- Each candidate aspect must receive **exactly one** of these three labels:

| Label | Meaning in one line |
|---|---|
| `explicit` | The aspect is directly mentioned in the post text. |
| `implicit` | The aspect is not named, but the post itself gives specific textual evidence that is sufficient to infer it. |
| `not_identifiable` | The post does not give enough textual evidence to identify the aspect. |

A single post usually produces several annotation decisions, one per candidate
aspect. Do not merge aspects, and do not add new aspects of your own.

The candidate aspects are provided by the source annotations. They are the
inputs to this task; you do not decide which aspects exist.

---

## 2. Label definitions

### `explicit`

Use `explicit` when the aspect is **directly mentioned** in the post.

- The mention may be an unambiguous name, alias, abbreviation, or direct
  reference that is understandable from the post itself.
- The evidence must be visible in the original post text.
- The aspect does not need to match the post character-for-character. For
  example, a full name in the aspect may appear as a surname in the post, as
  long as the reference is unambiguous using ordinary language in context.
- Hashtags and usernames can count as direct references only when the post text
  clearly and unambiguously refers to the candidate aspect. Do not use outside
  knowledge to decode them.
- Do not use `explicit` if you need outside knowledge, the image, or guesswork to
  connect the words in the post to the aspect.

### `implicit`

Use `implicit` when the aspect is **not directly named**, but the post provides
**specific textual evidence** that is sufficient to identify it through ordinary
language understanding alone.

- The inference must be supported by the post itself.
- The evidence is a textual clue: a phrase, a paraphrase, a description, a
  stated action, or another reference that points to the specific candidate
  aspect.
- The clue must support the **specific candidate aspect**, not merely the broad
  topic of the post.
- The connection must be strong enough that another careful reader, using only
  the post and ordinary language, would reach the same conclusion.
- Do not use external knowledge, association, speculation, likely context, or
  information that is only in the image.
- If the inference requires an unstated background fact or assumption, use
  `not_identifiable`.
- When uncertain between `implicit` and `not_identifiable`, choose
  `not_identifiable`.

A post being about the same general topic is **not** enough. The clue must make
the specific candidate aspect identifiable.

### `not_identifiable`

Use `not_identifiable` when the post does **not** provide enough textual
evidence to identify the candidate aspect.

- The aspect may be plausible, related to the topic, or commonly associated with
  something else in the post, but the connection is uncertain or unsupported by
  the post text.
- The aspect might require the image, external context, background knowledge, or
  information that is simply not present in the post.
- If the evidence is insufficient, this is the correct label. Do not force a
  weak connection into `implicit`.
- `not_identifiable` may still contain non-empty evidence when there is a
  relevant but insufficient textual clue. In that case, copy the clue exactly
  and explain in `reason` why it is insufficient.

`not_identifiable` is a normal and expected outcome. It is not a failure.

---

## 3. Strict annotation rules

1. Use only the original post text and the candidate aspect name.
2. Do not use external knowledge, including political, geographical, historical,
   cultural, or domain-specific knowledge.
3. Ordinary language understanding is allowed, but every implicit inference must
   be supported by specific evidence in the post itself.
4. Do not infer an aspect merely because it is commonly associated with another
   mentioned topic.
5. Mentioning a topic does not automatically establish a related action, policy,
   entity, or strategy.
6. If an inference requires unstated background knowledge or assumptions, choose
   `not_identifiable`.
7. When uncertain between `implicit` and `not_identifiable`, prefer
   `not_identifiable`.
8. A `not_identifiable` annotation may contain non-empty evidence if a relevant
   but insufficient textual clue exists.
9. Every non-empty evidence value must be an exact, contiguous substring of the
   original post text.
10. Confidence measures confidence in the assigned label, not sentiment
    intensity.

Additional clarifications:

- The post text must be used as written. Do not fix typos, expand abbreviations,
  translate, or paraphrase the source text.
- The candidate aspect name must be used as written. Case and punctuation in the
  aspect are part of the input.
- Do not use `background`, `surface`, or `thinking` annotations, images, source
  emotion labels, or sentiment labels.
- If the post is short, vague, or consists mostly of a hashtag, judge it on what
  is actually present. Short does not automatically mean `not_identifiable`, but
  missing evidence is missing evidence.

---

## 4. Topic mention, action, and direct support

These three things are not interchangeable:

### A topic being mentioned

The post names a broad subject, such as an issue, place, event, or field.

- A topic mention does **not** by itself state that a related action, policy,
  entity, or strategy is present.
- A topic mention does **not** by itself support a specific candidate aspect.

### An action being proposed or described

The post states that someone calls for, supports, opposes, plans, performs, or
will perform something.

- Only the action actually stated or described in the post counts.
- An action must still be specific enough to identify the candidate aspect
  without outside knowledge.
- A broad or vague action does not automatically establish a more specific
  candidate aspect.

### A candidate aspect being directly supported

The words of the post themselves name or describe the candidate aspect closely
enough that a careful reader can identify it using ordinary language alone.

- No unstated political, geographical, historical, cultural, or domain-specific
  fact may be required.

### Required distinctions

- Mentioning a topic does not establish a related action, policy, entity, or
  strategy.
- Mentioning a topic does not establish a specific candidate aspect.
- Common association is not textual evidence.
- External terminology or background knowledge cannot fill a gap in the post.
- A named location associated with hiring, employment, or an activity does not
  automatically establish a physical facility, office, factory, or other
  infrastructure.
- Only assign `implicit` when the text itself provides sufficient evidence for
  the specific candidate aspect.
- A relevant but insufficient clue can be retained as evidence for
  `not_identifiable`.

### Examples of these distinctions

- In P001, the post mentions `climate change`. That is a topic mention. It does
  not by itself establish `Climate action`, `Carbon tax`, `Green
  infrastructure`, `National carbon pricing strategy`, or any other specific
  climate policy.
- In P001, the post mentions a `first ministers meeting`. Do not use knowledge of
  Canadian political terminology to infer that this means `Provincial leaders`.
  That inference requires information not supplied by the post, so the aspect is
  `not_identifiable`.
- In P001, `Trudeau's` directly supports the aspect `Justin trudeau` through an
  ordinary language name reference. This is `explicit`.
- In P001, `first economic move` describes a broad economic action. It does not
  by itself establish `Economic recovery`.
- In P002, the post mentions `Harper Conservatives`, `the environment`, and `a
  strategy`. Those topic mentions do not establish `Keystone xl pipeline` or
  `Fossil fuel projects`.
- In P005, the text `in #PolandSpring, ME!` identifies a hiring location. It does
  not establish that a physical facility exists at that location. Therefore
  `Poland spring facility in maine` is `not_identifiable`, even though the
  location clue is relevant and can be retained as evidence.

---

## 5. Evidence requirements

For every decision, record all four fields below.

| Field | Requirement |
|---|---|
| `label` | Exactly one of `explicit`, `implicit`, or `not_identifiable`. |
| `evidence` | Exact, contiguous supporting words copied from the post, or an empty string `""`. |
| `reason` | A short explanation of why the label was assigned. |
| `confidence` | A number between `0` and `1`. |

Rules by label:

- **`explicit`**: `evidence` must be non-empty and must contain the direct
  mention or unambiguous reference from the post. `reason` should state that the
  aspect is directly mentioned.
- **`implicit`**: `evidence` must be non-empty and must show the specific textual
  clue that supports the inference. `reason` must explain the inference that
  connects the clue to the aspect using only the post and ordinary language.
- **`not_identifiable`**: `evidence` should be an empty string `""` unless there
  is a relevant but insufficient clue. If you include such a clue, keep it
  exact. `reason` must explain why the connection cannot be established.

Evidence rules:

- `evidence` must be a **verbatim, contiguous substring** of the post text
  whenever it is not empty. Do not paraphrase it, correct it, shorten it with
  ellipses, or join separate fragments with added text.
- Do not quote the candidate aspect as evidence unless those words actually
  appear in the post.
- Do not fabricate evidence spans.
- Keep `reason` brief, specific, and about this pair only.

Confidence rules:

- `confidence` measures how certain the annotator is that the **assigned label**
  is correct. It does not measure how certain the candidate aspect exists in the
  real world.
- For `not_identifiable`:
  - If the post contains no relevant clue for the candidate aspect, confidence
    should generally be high (for example, `0.90`–`1.00`).
  - If the post contains a relevant clue but that clue is insufficient to
    establish the candidate aspect, confidence may be lower depending on the
    ambiguity.
  - Do not assign low confidence merely because the candidate aspect is absent
    from the text.
  - Low confidence should reflect genuine uncertainty about which label is
    correct.
- Use the full `0` to `1` range when appropriate. A rough guide:
  - `0.90`–`1.00`: the label is very clear.
  - `0.70`–`0.89`: the label is fairly clear.
  - `0.50`–`0.69`: the decision is uncertain.
  - Below `0.50`: very uncertain, but still choose the best label.
- Confidence is not a substitute for choosing a label. Every pair still gets
  exactly one of the three labels.
- Do not force every score into identical values. Scores must reflect the actual
  certainty of each individual decision.

---

## 6. Examples using the pilot's actual records

These examples are illustrative. Always evaluate the actual post and aspect
pair rather than memorizing example labels.

### Example A

**Post:**

```text
Trudeau's first economic move if he were PM, call for a first ministers meeting on climate change. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Justin trudeau
```

**Expected label:** `explicit`

**Evidence:**

```text
Trudeau's
```

**Reason:**

```text
Trudeau's is a direct reference to Justin Trudeau using ordinary name recognition.
```

### Example B

**Post:**

```text
Trudeau's first economic move if he were PM, call for a first ministers meeting on climate change. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
National carbon pricing strategy
```

**Expected label:** `not_identifiable`

**Evidence:**

```text

```

**Reason:**

```text
The post mentions climate change and a meeting, but it does not describe a national carbon pricing strategy. A topic mention is not enough.
```

### Example C

**Post:**

```text
A caution. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Justin trudeau
```

**Expected label:** `not_identifiable`

**Evidence:**

```text

```

**Reason:**

```text
The post contains no textual reference or sufficient clue identifying Justin Trudeau.
```

### Example D

**Post:**

```text
Trudeau's first economic move if he were PM, call for a first ministers meeting on climate change. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Climate action
```

**Expected label:** `not_identifiable`

**Evidence:**

```text
climate change
```

**Reason:**

```text
The post mentions the topic of climate change, but it does not state a climate action. A relevant topic clue is not sufficient to identify this specific aspect.
```

### Example E

**Post:**

```text
Trudeau's first economic move if he were PM, call for a first ministers meeting on climate change. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Provincial leaders
```

**Expected label:** `not_identifiable`

**Evidence:**

```text
first ministers meeting
```

**Reason:**

```text
Inferring provincial leaders from a first ministers meeting requires Canadian political knowledge that the post does not provide.
```

### Example F

**Post:**

```text
Trudeau's first economic move if he were PM, call for a first ministers meeting on climate change. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Economic recovery
```

**Expected label:** `not_identifiable`

**Evidence:**

```text
first economic move
```

**Reason:**

```text
The post describes a broad economic move, but it does not mention or describe economic recovery.
```

### Example G

**Post:**

```text
Want to work at Nestle Waters NA? We're #hiring in #PolandSpring, ME! Click for details: http://t.co/r0oZRlUcEz
```

**Candidate aspect:**

```text
Poland spring facility in maine
```

**Expected label:** `not_identifiable`

**Evidence:**

```text
in #PolandSpring, ME!
```

**Reason:**

```text
The text identifies a hiring location, but it does not establish that a physical facility exists at that location. Do not infer a facility merely from a hiring location.
```

### Example H

**Post:**

```text
A caution. #cdnpoli #elxn42
```

**Candidate aspect:**

```text
Stephen harper
```

**Expected label:** `not_identifiable`

**Evidence:**

```text

```

**Reason:**

```text
The post contains no textual clue identifying this person.
```

**Confidence:** high, for example `0.95`, because the lack of identifying
evidence is clear.

---

## 7. Output format

Write **one JSON object per post–aspect pair**. Store the objects one per line
(JSON Lines) so that every pair is a separate, independently checkable record.
When a caller supplies a structured-output JSON Schema, follow that schema
exactly instead.

Each object must contain exactly these fields:

| Field | Type | Description |
|---|---|---|
| `pilot_id` | string | Pilot record identifier, for example `"P001"`. |
| `sample_id` | integer | Numeric dataset sample ID. |
| `aspect_index` | integer | Zero-based position of the aspect in the original `aspects` array. |
| `aspect` | string | Candidate aspect name, exactly as provided. |
| `label` | string | One of `explicit`, `implicit`, `not_identifiable`. |
| `evidence` | string | Verbatim post substring, or `""`. |
| `reason` | string | Short explanation of the label. |
| `confidence` | number | Value between `0` and `1`. |

Example object (illustrating format only):

```json
{
  "pilot_id": "P001",
  "sample_id": 2551,
  "aspect_index": 0,
  "aspect": "Justin trudeau",
  "label": "explicit",
  "evidence": "Trudeau's",
  "reason": "Trudeau's is a direct reference to Justin Trudeau.",
  "confidence": 0.95
}
```

Formatting rules:

- Preserve the original candidate aspect order. Iterate posts in pilot order and
  aspects in their original array order.
- Preserve candidate aspect names exactly. Do not rename, normalize, merge, or
  reorder them.
- Do not add fields that contain emotion labels or sentiment predictions.
- Use valid JSON. Escape quotation marks and backslashes correctly.
- Keep `evidence` empty (`""`) only when the label guidance allows it, as
  described in Section 5.
- The expected total is **508 objects** for the full pilot: one for every
  post–aspect pair.

---

## 8. Quality-control requirements

The following checks must be performed during validation:

- Every original post–aspect pair receives exactly one annotation.
- Only the three permitted labels are accepted: `explicit`, `implicit`,
  `not_identifiable`.
- No candidate aspects are silently dropped.
- Candidate aspect names and order match the pilot input exactly.
- Evidence must be traceable to the original post.
- Every non-empty evidence value is an exact, contiguous substring of the
  corresponding post.
- `explicit` and `implicit` annotations have non-empty evidence.
- Empty evidence is permitted for `not_identifiable`; non-empty evidence is also
  permitted for `not_identifiable` when it is a relevant but insufficient clue.
- Confidence must be a number between `0` and `1`.
- Confidence must reflect certainty in the assigned label, not certainty that the
  candidate aspect exists in the real world.
- A lack of textual evidence for an aspect is not, by itself, a reason for low
  confidence.
- Hiring, employment, or activity location clues must not be accepted as proof of
  a physical facility, office, factory, or other infrastructure.
- Invalid or malformed model responses must be flagged, not silently corrected.
- Emotion labels remain separate from the explicitness annotations.
- The total record count must match the number of post–aspect pairs.
- Duplicate annotations for the same `(pilot_id, aspect_index)` pair must be
  rejected.
- The annotation must not depend on images, external context, external knowledge,
  or the `background`, `surface`, or `thinking` files.
- A topic mention alone must not be accepted as support for a related action,
  policy, entity, or strategy.
- An inference that depends on unstated background knowledge must be rejected and
  labeled `not_identifiable`.

When a response fails a check, report the exact failure. Do not repair it
silently, and do not guess what the model intended.

---

## 9. Important project limitation

This is the **text-only annotation phase** of a multimodal project.

The labels produced here describe only what can be established from the
original post text. They do **not** establish whether an aspect could be
identified using the accompanying image. An aspect labeled `not_identifiable`
in this phase might still be identifiable from the image, and an aspect labeled
`explicit` or `implicit` is judged only on text evidence.

A future image-assisted experiment would need a separate annotation protocol,
its own guidelines, and its own validation. Do not use image information in this
phase, and do not treat these labels as image-aware ground truth.
