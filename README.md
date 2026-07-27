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
