# Provenance Guard — Planning Document

Written before any implementation code. Updated before any stretch features.

---

## Detection Signals

### Signal 1 — LLM Classifier (Groq / llama-3.3-70b-versatile)

**What it measures:** Semantic and stylistic coherence holistically. The model reads the text and assesses whether it carries the hallmarks of AI output: characteristic hedging phrases ("it is important to note"), over-structured argumentation, unnaturally smooth transitions, uniform register, absence of genuine personal voice.

**Output format:** A float between 0.0 and 1.0, where 1.0 = high confidence the text is AI-generated, 0.0 = high confidence it is human-written. Extracted from the model's structured JSON response.

**Prompt contract:** The Groq call will instruct the model to return exactly:
```json
{"ai_score": <float 0.0–1.0>, "reasoning": "<one sentence>"}
```
The `reasoning` field is logged but not returned to the user.

**What it misses:** Edited AI output (a human who adds a personal anecdote on top of generated text), highly polished human prose that reads as impersonal, and non-native English speakers whose careful formal register resembles AI output.

---

### Signal 2 — Stylometric Heuristics (pure Python)

**What it measures:** Three surface-level statistical properties:

1. **Sentence length variance** — standard deviation of word counts per sentence. AI text clusters around a comfortable medium; human writing is more irregular.
2. **Type-token ratio (TTR)** — unique words / total words. Lower TTR = more repetitive vocabulary, a tendency in AI output.
3. **Punctuation density** — punctuation marks / total words. AI text tends toward clean, rule-following prose; human writing uses punctuation more idiosyncratically.

**Output format:** Each metric is individually computed, then normalized to a 0.0–1.0 sub-score where 1.0 = more AI-like. The three sub-scores are averaged into a single `stylometric_score` float.

Normalization approach:
- Sentence length variance: low variance → high score. Map via `1 - min(variance / 30, 1)` (variance of 0 → score 1.0; variance ≥ 30 → score 0.0).
- TTR: low TTR → high score. Map via `1 - min(ttr / 0.8, 1)` (TTR of 0 → score 1.0; TTR ≥ 0.8 → score 0.0).
- Punctuation density: moderate density → neutral, very low or very high → adjust. Map via `1 - min(density / 0.15, 1)` (no punctuation → score 1.0; dense punctuation → score 0.0).

**What it misses:** Short texts under ~80 words (TTR is unreliable at small sample sizes), genre-specific writing (legal briefs and technical documentation are structurally uniform by convention), and AI text that has been prompted to write casually and introduces deliberate irregularity.

---

### Combining the Two Signals

**Weighting:** The LLM classifier carries more weight because it captures semantic patterns the heuristics cannot:

```
confidence = (llm_score * 0.65) + (stylometric_score * 0.35)
```

**Rationale for 65/35 split:** Stylometric heuristics are genre-sensitive and unreliable on short texts. The LLM signal is more robust across content types. However, stylometrics provide an independent structural check — if the LLM score is borderline and stylometrics agree, confidence rises; if they disagree, the combined score sits in the uncertain zone, which is the correct behavior.

---

## Uncertainty Representation

### What confidence scores mean

| Score range | Meaning |
|-------------|---------|
| 0.00 – 0.35 | Likely human-written. Both signals lean human, or LLM leans human strongly. |
| 0.36 – 0.74 | Uncertain. Signals disagree, or both are weakly confident. Do not assert a verdict. |
| 0.75 – 1.00 | Likely AI-generated. Both signals agree with moderate-to-high strength. |

**Why the uncertain band is wide (0.36–0.74):** A narrow uncertain zone (e.g., 0.45–0.55) would force confident-looking labels onto scores that don't warrant them. A score of 0.68 represents a system that sees some evidence of AI patterns but not enough to stake a claim. Given that false positives are worse than false negatives on a writing platform, the uncertain band should err toward caution.

**What 0.60 means specifically:** The LLM thinks the text is moderately AI-like (say, llm_score ≈ 0.72) but stylometrics are weakly signaling human patterns (stylometric_score ≈ 0.37). The signals disagree. The combined score lands in the uncertain zone. The correct label is uncertain — not "likely AI."

**What 0.51 vs. 0.95 means for the label:** Both are above 0.5, but they produce different labels. 0.51 falls in the uncertain band and gets the uncertain label. 0.95 falls in the high-confidence AI band and gets the definitive AI label. The threshold at 0.75 is where the system is willing to make a strong claim.

### Calibration notes

Raw signal outputs are not adjusted further beyond the normalization described in Signal 2. The 65/35 weighting is the calibration mechanism. If testing shows scores cluster too high (most submissions land above 0.6), the sentence length variance normalization ceiling (currently 30) should be raised to spread the distribution.

---

## Transparency Label Design

Three variants. Written here verbatim — the label generator will return exactly these strings.

### High-confidence AI (confidence ≥ 0.75)

> **AI-assisted content detected**
> Our system found strong indicators that this content was likely generated or substantially written by an AI tool (confidence: {confidence_pct}%). If this classification is wrong, the creator can submit an appeal.

### Uncertain (confidence 0.36–0.74)

> **Attribution unclear**
> Our system found mixed signals for this content and cannot confidently determine whether it was written by a human or generated by AI (confidence: {confidence_pct}%). We've flagged it for transparency, but the creator may contest this classification through an appeal.

### High-confidence human (confidence ≤ 0.35)

> **Appears human-written**
> Our system found strong indicators that this content was written by a human (confidence: {confidence_pct}% human). No action is required.

### Notes on label design

- `{confidence_pct}` is rendered as `round((1 - confidence) * 100)` for the human label and `round(confidence * 100)` for the AI label, so the number always expresses confidence in the stated verdict, not in AI-ness specifically.
- All three variants are reachable through the submission endpoint by submitting different content types. This will be verified during Milestone 5 testing.
- Every label except the human-written variant mentions appeals. The human-written label does not — there is nothing to appeal.

---

## Appeals Workflow

### Who can appeal
Any creator who has a `content_id` from a prior `/submit` response. The system does not authenticate or verify identity — the `content_id` is the credential. In a production system, this would be gated behind session auth, but that is out of scope here.

### What they provide
- `content_id` — the UUID from their submission response (required)
- `creator_reasoning` — a free-text explanation of why the classification is wrong (required, no length limit enforced)

### What the system does on appeal receipt
1. Looks up the record by `content_id`. Returns 404 if not found.
2. Updates the record's `status` field from `"classified"` to `"under_review"`.
3. Appends to the audit log entry: `appeal_reasoning`, `appeal_timestamp`, updated `status`.
4. Returns confirmation: `{content_id, status: "under_review", message}`.

No automated re-classification. No score is recalculated. The appeal is a human-review trigger, not a pipeline re-run.

### What a human reviewer sees in the appeal queue (GET /log)
For any entry with `status: "under_review"`, the log exposes:
- Original `attribution`, `confidence`, `llm_score`, `stylometric_score`
- The label text that was shown to the user
- `appeal_reasoning` (creator's verbatim explanation)
- `appeal_timestamp`

The individual signal scores are the key piece — a reviewer can see whether the signals agreed (strong case) or disagreed (ambiguous case worth reviewing closely). A non-native speaker explaining their formal register alongside a `stylometric_score` of 0.61 and `llm_score` of 0.74 gives a reviewer enough to make an informed judgment.

---

