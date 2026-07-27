# Provenance Guard

Provenance Guard is a Flask API that classifies submitted text as AI-generated or human-written. It runs two independent detection signals — a Groq LLM classifier and a set of stylometric heuristics — combines their outputs into a calibrated confidence score, and returns a transparency label explaining the result to the creator. Creators who dispute a classification can submit an appeal, which is logged alongside the original decision for human review.

The system is designed for writing platforms that need to surface AI-generated content to their users without making overconfident claims. False positives — flagging human writing as AI — are treated as more damaging than false negatives, which is reflected in the wide uncertain band (0.36–0.74) and the 65/35 signal weighting that prevents the system from asserting a verdict when evidence is mixed.

---

## Architecture

A submission enters through the rate-limited `POST /submit` endpoint. Both signals run on the raw text in the same request, the confidence scorer combines their outputs, the label generator maps the score to one of three verbatim label strings, and the audit logger writes the complete structured entry to SQLite — all before the response is returned.

An appeal enters through `POST /appeal`, which looks up the record by `content_id` (404 if not found), updates its status, and appends the creator's reasoning to the same audit log entry. No re-classification occurs.

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
                  │
                  ▼
         ┌─────────────────┐
         │ Confidence      │
         │ Scorer          │
         │ (0.65/0.35 mix) │
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

**Storage:** SQLite (`audit_log.db`) via `db.py`. All signal scores, confidence, attribution, label, and appeal data are written to a single `audit_log` table. `GET /log` returns the 20 most recent entries as JSON.

---

## Confidence Scoring

The confidence score is a weighted blend of the two signals: `0.65 × llm_score + 0.35 × stylometric_score`. Scores ≥ 0.75 map to `likely_ai`, ≤ 0.35 map to `likely_human`, and everything in between is `uncertain`. The wide uncertain band is intentional — the system treats false positives as more costly than false negatives.

The examples below are taken from Milestone 4 testing and show that the scorer produces real variation across inputs, not a constant output.

**Example 1 — high confidence AI-generated text**

Input (formal, uniform-sentence-length AI prose):
```
Artificial intelligence (AI) has emerged as a transformative technology with
far-reaching implications across numerous sectors. It is important to note that
its impact extends beyond mere automation, encompassing complex decision-making
processes that were previously exclusive to human cognition. Furthermore, the
integration of machine learning algorithms has enabled unprecedented advancements
in data analysis and pattern recognition.
```

Response:
```json
{
  "attribution": "likely_ai",
  "confidence": 0.7665,
  "llm_score": 0.9,
  "stylometric_score": 0.5186,
  "label": "AI-assisted content detected. Our system found strong indicators that this content was likely generated or substantially written by an AI tool (confidence: 77%). If this classification is wrong, the creator can submit an appeal."
}
```

**Example 2 — lower confidence, human-written text**

Input (casual, conversational, irregular punctuation):
```
i was making eggs this morning and dropped the whole carton on the floor. like,
all 12. just gone. the dog was thrilled obviously. i just stood there for a second
not sure if i should laugh or cry, decided on both
```

Response:
```json
{
  "attribution": "likely_human",
  "confidence": 0.2825,
  "llm_score": 0.2,
  "stylometric_score": 0.4356,
  "label": "Appears human-written. Our system found strong indicators that this content was written by a human (confidence: 72% human). No action is required."
}
```

The 0.484-point gap between these two cases (0.7665 vs 0.2825) spans the full `likely_ai`-to-`likely_human` range and reflects genuine signal agreement: the LLM score alone moves from 0.9 to 0.2, while stylometrics shift less dramatically (0.52 → 0.44) because the human text's short sentences and low punctuation density push the stylometric score toward the uncertain band.

---

## Known Limitations

**Formal human writing is the system's most likely false-positive source.** The sentence length variance heuristic treats low variance as an AI signal — but low variance is also a property of careful, edited prose. A short scientific abstract with four sentences averaging 11–13 words each produces a `sent_score` near 0.95, indistinguishable from AI output. A formal academic text tested against the system returned `stylometric_score: 0.3631` — near the human boundary — only because its low type-token ratio (domain vocabulary repeated across sentences) partially cancels the sentence regularity signal. That cancellation is accidental, not designed. A slightly longer abstract where the domain terms don't repeat as much would push the stylometric score higher and pull the overall confidence toward `uncertain` or beyond. There is no feature in the stylometric signal that distinguishes "uniform because AI" from "uniform because edited."

The LLM signal compounds this for formal writing. The classifier (Llama-3.3-70b-versatile) is a general-purpose language model, not a purpose-built detector. It was trained on a corpus that includes large amounts of AI-generated text, which skews toward formal, structured prose. When a human writes in that register — grant proposals, medical summaries, technical reports — the model has less basis for distinguishing it from AI output and tends to return elevated `ai_score` values. Since the LLM carries 65% of the final weight, a moderate LLM score on formal human text is enough to land the result in the uncertain band or above even if the stylometrics are neutral.

The practical consequence: the system is more reliable for clearly casual human text than for carefully edited human text, and more reliable for generic AI output than for AI text that was prompted to sound informal or first-person. Content in the uncertain band (confidence 0.36–0.74) should not be acted on without human review — the wide band exists precisely because these signals cannot resolve ambiguous cases.
