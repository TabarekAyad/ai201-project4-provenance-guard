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
confidence = (llm_score * 0.55) + (stylometric_score * 0.45)
```

**Rationale for 55/45 split:** The initial weighting was 65/35 (LLM/stylometric). Calibration testing on four labeled inputs showed that at 65/35 the stylometric signal had negligible influence on borderline cases — the gap between a clearly-AI input and a clearly-human input was only 0.018 stylometric points, effectively noise, and the LLM score alone was deciding the outcome. After rebuilding the stylometric function with AI phrase markers and human-voice markers (in addition to the original three surface metrics), the weight was adjusted to 55/45. The lower LLM share gives the retooled stylometric signal meaningful leverage on borderline calls while keeping the LLM's holistic read as the dominant input. A 55/45 blend still gives the LLM the largest share while allowing calibrated stylometric evidence to lift clearly AI-like generic prose above the AI threshold and keep lightly edited AI output in the uncertain zone.

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

The stylometric signal combines surface metrics with lightweight phrase/register markers and casual human-voice markers. The 55/45 weighting is the final calibration mechanism. If testing shows scores cluster too high (most submissions land above 0.6), the phrase marker list should be narrowed or the marker component should be weighted down.

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

## Anticipated Edge Cases

### 1. Non-native English speaker writing formally
A writer whose second language is English tends to write carefully: measured vocabulary, even sentence rhythm, hedged claims. The LLM classifier reads the diplomatic register as AI-like. The stylometric signal sees low sentence-length variance and moderate TTR. Both signals fire in the wrong direction. Combined score: potentially 0.65–0.75, landing in the uncertain or low-AI band. Mitigation: the wide uncertain band absorbs many of these cases. The appeal workflow handles the rest. The label in the uncertain zone explicitly invites appeal.

### 2. Very short text (under 80 words)
A haiku, a two-sentence bio, a single paragraph. The TTR metric is unreliable at small sample sizes — any short text has high unique-word ratios by definition. Sentence length variance is unstable with 2–3 sentences. The stylometric signal is effectively noise. The LLM signal still carries the largest share of the combined score (55/45), but the stylometric component should not be trusted for very short text. Mitigation: log a warning internally when text is under 80 words; do not surface it to users. Consider widening the uncertain band for short texts in a future version.

### 3. Highly structured human writing (legal, academic, technical)
A legal brief or academic abstract written by a human is uniformly structured by professional convention: formal register, low variance, moderate vocabulary, minimal punctuation eccentricity. The stylometric signal will flag it as AI-like. The LLM may also flag the impersonal register. This is a genre-blind failure mode for both signals. Mitigation: none within the current pipeline — this is an acknowledged limitation to document in the README.

---

## Architecture

### Diagram

```
FLOW 1: SUBMISSION
──────────────────

  Client
    │
    │  POST /submit  {text, creator_id}
    ▼
┌─────────────┐
│ Rate Limiter│  ── 429 if over limit ──────────────────────────────► Client
└──────┬──────┘
       │  {text, creator_id}
       ▼
┌──────────────────┐
│ Submission       │  generates content_id (UUID)
│ Endpoint         │
│ POST /submit     │
└───┬──────────────┘
    │                          │
    │  raw text                │  raw text
    ▼                          ▼
┌──────────────┐       ┌──────────────────────┐
│ Signal 1     │       │ Signal 2             │
│ LLM          │       │ Stylometric          │
│ Classifier   │       │ Heuristics           │
│ (Groq API)   │       │ (pure Python)        │
└──────┬───────┘       └──────────┬───────────┘
       │  llm_score (0–1)         │  stylometric_score (0–1)
       └──────────┬───────────────┘
                  │  llm_score + stylometric_score
                  ▼
         ┌─────────────────┐
         │ Confidence      │
         │ Scorer          │
         │ (0.55/0.45 mix) │
         └────────┬────────┘
                  │  confidence (0–1) + attribution
                  ▼
         ┌─────────────────┐
         │ Label           │
         │ Generator       │
         └────────┬────────┘
                  │  label text (verbatim string)
                  ▼
         ┌─────────────────┐
         │ Audit Logger    │  writes structured entry to SQLite
         └────────┬────────┘
                  │
                  ▼
    {content_id, attribution, confidence, label, status} ──► Client


FLOW 2: APPEAL
──────────────

  Client
    │
    │  POST /appeal  {content_id, creator_reasoning}
    ▼
┌──────────────────┐
│ Appeal Endpoint  │
└───┬──────────────┘
    │  content_id
    ▼
┌──────────────────┐
│ Storage Lookup   │  ── 404 if not found ───────────────────────────► Client
└───┬──────────────┘
    │  record found
    ▼
┌──────────────────┐
│ Status Update    │  "classified" → "under_review"
└───┬──────────────┘
    │  updated record + creator_reasoning
    ▼
┌──────────────────┐
│ Audit Logger     │  appends appeal_reasoning, appeal_timestamp
└───┬──────────────┘
    │
    ▼
    {content_id, status: "under_review", message} ──► Client
```
### Narrative

A submission enters through the rate-limited `/submit` endpoint, which orchestrates the full pipeline: both signals run on the raw text, the confidence scorer combines their outputs using a 55/45 weighted average, the label generator maps the score to verbatim label text, and the audit logger writes the complete structured entry to SQLite before the response is returned. An appeal enters through `/appeal`, which looks up the existing record by `content_id`, updates its status, and appends the creator's reasoning to the same audit log entry — no re-classification occurs.

---

## AI Tool Plan

### Milestone 3 — Submission endpoint + Signal 1

**Sections to provide:** Detection Signals (Signal 1 only), Architecture diagram (Flow 1 only), API surface contract for `POST /submit`.

**What to ask for:** Flask app skeleton with `POST /submit` route stub that accepts `{text, creator_id}` and returns a hardcoded response; plus the `classify_with_llm(text)` function that calls Groq with the structured prompt and returns `llm_score` as a float.

**How to verify:** Call `classify_with_llm()` directly with the four test inputs from the spec (clearly AI, clearly human, two borderline). Confirm the function returns a float between 0 and 1 and that the clearly-AI input scores noticeably higher than the clearly-human input before wiring into the endpoint.

---

### Milestone 4 — Signal 2 + confidence scoring

**Sections to provide:** Detection Signals (Signal 2), Uncertainty Representation (thresholds + weighting), Architecture diagram (confidence scorer box).

**What to ask for:** `compute_stylometrics(text)` function that returns `stylometric_score` as a float; plus `compute_confidence(llm_score, stylometric_score)` that applies the 55/45 weighting and returns `{confidence, attribution}`.

**How to verify:** Run all four test inputs through both signals independently and print scores side by side. Check that clearly-AI input scores above 0.75 and clearly-human input scores below 0.35. If borderline inputs land in 0.36–0.74, the scorer is calibrated correctly.

---

### Milestone 5 — Production layer

**Sections to provide:** Transparency Label Design (all three variants verbatim), Appeals Workflow, Architecture diagram (both flows), API surface contract for `POST /appeal` and `GET /log`.

**What to ask for:** `generate_label(confidence, attribution)` function that returns verbatim label text; `POST /appeal` endpoint implementation; Flask-Limiter setup on `/submit`; `GET /log` endpoint.

**How to verify:** Submit inputs targeting each confidence zone and confirm all three label variants are returned. Submit an appeal for a known `content_id` and confirm `GET /log` shows `status: "under_review"` and `appeal_reasoning` populated. Run 12 rapid requests to `/submit` and confirm requests 11–12 return 429.

