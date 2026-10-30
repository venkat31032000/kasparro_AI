# Kasparro AI Visibility Evaluation

**Kasparro AI Engineer Assignment — AI Visibility Analysis and Human Review**

> **AI interprets. Code decides.**

A runnable FastAPI backend that ingests archived responses from ChatGPT, Gemini, and Google AI Mode, performs evidence-grounded semantic analysis, calculates transparent deterministic visibility scores, produces diagnostics and remedies, and enforces human review before report export.

---

# 1. Overview

This project analyzes the supplied Kasparro historical AI-answer snapshot containing:

- 50 prompts
- 150 archived responses
- 50 ChatGPT responses
- 50 Gemini responses
- 50 Google AI Mode responses
- 2,439 supplied citation occurrences

The source snapshot was captured on **31 July 2026**, in **India**, in **English**, through DataForSEO.

It should therefore be interpreted as a historical snapshot of those captured AI experiences, not as a current market ranking or as direct live calls to each vendor.

The backend answers three main questions:

1. Where does Kasparro appear to be winning or losing in this snapshot?
2. What response-level evidence supports those findings?
3. What should be investigated or changed next?

The system also implements a human-review workflow so that only an explicitly approved, immutable report version may be exported.

---

# 2. Design Principle

The main architectural principle is:

> **AI interprets. Code decides.**

The LLM performs semantic interpretation where language understanding is useful.

Deterministic application code controls everything that must be reproducible or security-sensitive.

## AI responsibilities

The semantic model determines:

- whether Kasparro is mentioned;
- whether Kasparro is recommended;
- whether Kasparro is negatively characterized;
- explicitly named competitors;
- recommendation position when observable;
- evidence excerpts supporting the classification.

## Deterministic code responsibilities

Application code controls:

- input validation;
- output validation;
- evidence verification;
- scoring;
- exact counts;
- aggregation;
- retry limits;
- result accounting;
- persistence;
- configuration identity;
- idempotency;
- authorization;
- report state transitions;
- review expiry;
- version control;
- export eligibility.

The LLM therefore cannot approve a report, change permissions, calculate arbitrary scores, or manufacture unsupported evidence.

---

# 3. Architecture

```text
Supplied Pack
     |
     v
Dataset Import + Validation
     |
     v
SQLite Persistence
     |
     v
Analysis Run
     |
     +-----------------------------+
     |                             |
     v                             v
Live LLM Adapter            Replay Baseline
     |                             |
     +--------------+--------------+
                    |
                    v
          Structured Model Output
                    |
                    v
            Output Validation
                    |
                    v
          Exact Evidence Check
                    |
                    v
         Deterministic Scoring
                    |
                    v
       Persist Analysis Result
                    |
                    v
       Aggregation / Findings
                    |
                    v
             Report Draft
                    |
                    v
           Analyst Submission
                    |
                    v
       Immutable Submitted Version
                    |
                    v
             Reviewer Decision
              /            \
             v              v
         Approved        Rejected
             |
             v
           Export
```

---

# 4. Technology

The implementation uses:

- Python 3.10+
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- Pydantic Settings
- OpenAI-compatible model adapter
- HTTPX
- Pytest
- Uvicorn

SQLite was deliberately selected because the assignment workload contains only 150 archived responses and does not require distributed infrastructure.

---

# 5. Repository Structure

The repository is organized around clear boundaries between API handling, persistence, semantic analysis, deterministic scoring, evaluation, and tests.

A representative structure is:

```text
kasparro_AI/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── scoring.py
│   ├── validation.py
│   ├── routers/
│   └── services/
│
├── evaluation/
│   ├── fixtures/
│   │   ├── gold_cases.json
│   │   └── synthetic_cases.json
│   ├── grader.py
│   ├── live_repeat.py
│   ├── live_repeat_results.json
│   └── README.md
│
├── tests/
│   ├── test_analysis.py
│   └── test_reports.py
│
├── docs/
│   ├── Kasparro_Evaluation_Results.pdf
│   └── Kasparro_Analysis_Output.pdf
│
├── data/
├── fixtures/
├── provenance/
├── reference/
├── schemas/
├── tools/
│
├── analysis_output.json
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
├── README.md
└── DECISION_NOTE.md
```

The supplied/private source data and provenance should remain outside public Git history.

---

# 6. Input Handling

The supplied dataset contains:

```text
data/prompts.jsonl
data/responses.jsonl
data/citations.jsonl
data/run.json
data/READ_ME.txt
reference/
provenance/provider_payloads.jsonl
schemas/
fixtures/
```

Original IDs and source records are preserved.

Missing metadata is not invented.

For example, if the source does not contain a model version, the value remains unknown/null rather than being inferred.

`answer_text` and `answer_markdown` are treated as two representations of the same archived response.

Citation occurrences are preserved separately from semantic claims about whether those citations actually support a statement.

Citation presence is observable.

Citation entailment/support is not assumed.

---

# 7. Semantic Classification

Every archived response is analyzed into a structured result.

The minimum semantic labels are:

```text
absent
mentioned
recommended
negatively characterized
```

Labels may overlap where justified.

For example:

```text
mentioned = true
negative = true
```

is valid.

However:

```text
recommended = true
mentioned = false
```

is invalid.

A mention is therefore **not automatically a recommendation**.

The model can additionally extract:

- competitors;
- recommendation position;
- evidence excerpts;
- confidence-related structured output where applicable.

---

# 8. Evidence Validation

Evidence returned by the model must correspond to the archived response.

An evidence excerpt is accepted only when it can be located in the source answer.

Unsupported evidence is rejected.

The validation layer also rejects logically inconsistent model output.

Examples include:

```text
recommended = true
mentioned = false
```

and:

```text
recommendation_position = 2
recommended = false
```

This prevents structurally valid JSON from automatically becoming a trusted semantic result.

Malformed, empty, inconsistent, or unsupported model output is retried within a bounded retry policy.

If valid output cannot be obtained, the response becomes an explicit failure.

---

# 9. Visibility Score

The deterministic score is versioned as:

```text
visibility-v1
```

The current components are:

| Component | Weight |
|---|---:|
| Kasparro mentioned | +30 |
| Kasparro recommended | +40 |
| Recommendation position #1 | +20 |
| Recommendation position #2 | +15 |
| Recommendation position #3 | +10 |
| Kasparro citation present | +10 |
| Negative characterization | -30 |

The final score is clamped to:

```text
0 <= visibility_score <= 100
```

Example scores:

```text
Absent                         0
Mention only                  30
Recommendation                70
Recommendation at #1          90
Recommendation at #2          85
Recommendation at #3          80
Mention + Kasparro citation   40
Negative mention               0
```

The score is deliberately simple and transparent rather than presented as a statistically calibrated business metric.

Most importantly:

> **A failed analysis is not a successful zero-score observation.**

Failed analyses store no valid visibility score.

---

# 10. Response Accounting

Every one of the 150 supplied responses must reach a terminal state:

```text
success
failed
skipped
```

This makes coverage explicit.

The final persisted live analysis produced:

```text
Total responses : 150
Success         : 148
Failed          : 2
Skipped         : 0
Accounted       : 150
Success coverage: 98.7%
```

The two failures remain visible rather than being silently converted into absence/zero-score observations.

---

# 11. Execution Modes

The application distinguishes execution modes so results are not confused across model-backed and deterministic execution.

## Live

Uses the configured model adapter for semantic classification.

## Replay

Uses a deterministic local baseline.

Replay is useful for:

- keyless execution;
- application demonstrations;
- testing;
- deterministic evaluation;
- failure-path verification.

Replay is **not** presented as evidence of live-model semantic quality.

Execution mode is part of the analysis configuration identity.

---

# 12. Model Configuration

Model configuration is loaded from environment variables.

The final persisted live analysis used:

```text
Model          : gpt-6-luna
Prompt version : semantic-classification-v2
Scoring version: visibility-v1
```

Live model outputs are probabilistic and may vary between runs.

The application therefore persists configuration identity with analysis results.

---

# 13. Retries and Failure Handling

Model calls use bounded retry behavior.

The system handles:

- provider failure;
- timeout;
- malformed output;
- empty output;
- unsupported evidence;
- invalid semantic combinations.

One bad response does not erase successfully processed responses.

Completed successful results are preserved during retries and resumed analysis.

---

# 14. Idempotency and Resume

Analysis configuration includes relevant identity such as:

- execution mode;
- model;
- semantic prompt version;
- scoring version.

A matching analysis can therefore be resumed.

Successfully completed response results are reused instead of duplicated.

This supports:

- retry after partial failure;
- process restart;
- repeated analysis requests;
- deterministic explanation of reuse versus recomputation.

The final live run demonstrates this behavior.

An earlier execution produced:

```text
141 successful results
9 failures
```

Inspection showed that several failures were caused by semantic outputs whose evidence did not exactly satisfy the evidence validator.

The validator was **not weakened**.

Instead, invalid semantic output became retryable within the existing bounded retry policy.

The same analysis was resumed.

Final result:

```text
148 successful results
2 explicit failures
```

Already completed successful results were not duplicated.

---

# 15. Exactly-Once Limitation

The application can enforce uniqueness and idempotency for persisted database results.

It cannot guarantee exactly-once billing at the external model-provider boundary.

For example:

1. the provider completes a model request;
2. the process crashes before the local transaction records success;
3. the resumed analysis may need to repeat that external request.

Therefore:

- persisted result duplication is prevented;
- retries are bounded;
- configuration identity is preserved;
- external model billing is not claimed to be exactly-once.

---

# 16. API

The application exposes a FastAPI service.

Start it with:

```powershell
uvicorn app.main:app --reload
```

Default local URL:

```text
http://127.0.0.1:8000
```

Health endpoint:

```text
GET /health
```

Interactive generated API documentation:

```text
http://127.0.0.1:8000/docs
```

OpenAPI schema:

```text
http://127.0.0.1:8000/openapi.json
```

---

# 17. Main API Capabilities

Primary routes include:

```text
POST   /datasets

POST   /analyses
GET    /analyses/{analysis_id}
GET    /analyses/{analysis_id}/results

POST   /reports
PATCH  /reports/{report_id}
POST   /reports/{report_id}/submit
POST   /reports/{report_id}/decision
GET    /reports/{report_id}/export

GET    /health
```

Analysis result listings support bounded pagination and filtering.

---

# 18. Human Review

Two local identities are configured:

```text
analyst
reviewer
```

Authorization is derived from backend-configured bearer tokens.

A caller cannot gain reviewer authority by placing:

```json
{
  "role": "reviewer"
}
```

in a request body.

## Analyst permissions

The analyst can:

- import data;
- run analysis;
- create reports;
- edit drafts;
- submit a report version.

## Reviewer permissions

The reviewer can:

- inspect a submitted version;
- approve it;
- reject it;
- provide a review comment.

The reviewer cannot perform analyst-only report creation actions.

The analyst cannot approve their own report using analyst credentials.

---

# 19. Report State Machine

Report versions use:

```text
draft
submitted
approved
rejected
```

Workflow:

```text
draft
  |
  v
submitted
 /      \
v        v
approved rejected
```

Submission freezes the version being reviewed.

Editing a submitted or approved report does not mutate the reviewed artifact.

Instead:

```text
v1 approved
    |
    +---- edit ----> v2 draft
```

The old approved `v1` remains immutable.

The new `v2` requires independent review before it can be exported.

---

# 20. Review Expiry and Conflicts

Review expiry is enforced server-side.

Pending review state is persisted and therefore survives application restart.

The backend also protects against:

- stale edits;
- repeated decisions;
- incompatible version changes;
- export after unapproved edits.

Optimistic version checks reject stale modifications.

Repeated approval/rejection attempts return a conflict rather than silently overwriting the existing review decision.

---

# 21. Export Safety

Only an explicitly approved report version can be exported.

Export is refused for:

```text
draft
submitted
rejected
```

content.

If:

```text
v1 = approved
v2 = draft
```

then:

```text
v1 -> export allowed
v2 -> export refused
```

This ensures that an approval authorizes one immutable artifact rather than whatever content happens to be current.

---

# 22. Environment Setup

Python 3.10 or later is recommended.

## Windows PowerShell

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and provide the required configuration.

---

# 23. Environment Variables

Example `.env.example`:

```env
DATABASE_URL=sqlite:///./kasparro.db

LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=gpt-6-luna

ANALYST_TOKEN=local-analyst-token
REVIEWER_TOKEN=local-reviewer-token
```

Additional timeout/output configuration should match the fields defined in `app/config.py`.

Real secrets belong only in `.env`.

Do **not** commit `.env`.

---

# 24. Database Initialization

The project uses SQLAlchemy models and SQLite.

On application startup, the configured schema is created using the SQLAlchemy metadata initialization performed by the application.

For a clean local run, configure:

```env
DATABASE_URL=sqlite:///./kasparro.db
```

and start:

```powershell
uvicorn app.main:app --reload
```

The required tables will be initialized against the configured database.

SQLite was selected for the assignment because it provides persistence across restarts without introducing unnecessary infrastructure.

---

# 25. Running the Application

From the project root:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Verify:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Then open:

```text
http://127.0.0.1:8000/docs
```

for the exact generated request schemas.

---

# 26. Example Workflow

The intended application workflow is:

```text
Import
   |
   v
Analyse
   |
   v
Inspect Results
   |
   v
Create Report
   |
   v
Edit Draft
   |
   v
Submit Version
   |
   v
Reviewer Decision
   |
   v
Export Approved Version
```

Because FastAPI generates the exact request schema from the running code, `/docs` is the authoritative source for payload fields.

---

# 27. Import Dataset

Analyst authentication:

```text
Authorization: Bearer local-analyst-token
```

Example:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/datasets" `
  -H "Authorization: Bearer local-analyst-token" `
  -H "Content-Type: application/json" `
  -d "@dataset-request.json"
```

Use `/docs` for the exact dataset request contract.

Original source IDs are preserved during import.

Repeated imports are handled idempotently rather than creating uncontrolled duplicate source records.

---

# 28. Start an Analysis

Example conceptual request:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/analyses" `
  -H "Authorization: Bearer local-analyst-token" `
  -H "Content-Type: application/json" `
  -d "@analysis-request.json"
```

A replay configuration can be used for keyless deterministic execution.

A live configuration uses the configured model adapter.

Use `/docs` for the exact request fields supported by the current implementation.

---

# 29. Inspect Analysis

Summary:

```powershell
curl.exe "http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID"
```

Paginated results:

```powershell
curl.exe "http://127.0.0.1:8000/analyses/YOUR_ANALYSIS_ID/results?limit=25&offset=0"
```

Results can also be filtered using the query parameters exposed in `/docs`.

---

# 30. Create and Edit Report

Create:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/reports" `
  -H "Authorization: Bearer local-analyst-token" `
  -H "Content-Type: application/json" `
  -d "@report-create.json"
```

Edit:

```powershell
curl.exe -X PATCH "http://127.0.0.1:8000/reports/YOUR_REPORT_ID" `
  -H "Authorization: Bearer local-analyst-token" `
  -H "Content-Type: application/json" `
  -d "@report-update.json"
```

Edits include an expected version so stale updates can be rejected.

---

# 31. Submit Report

Example:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/reports/YOUR_REPORT_ID/submit" `
  -H "Authorization: Bearer local-analyst-token" `
  -H "Content-Type: application/json" `
  -d "@submit-request.json"
```

Submission freezes the selected version.

---

# 32. Reviewer Decision

Reviewer authentication:

```text
Authorization: Bearer local-reviewer-token
```

Approve:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/reports/YOUR_REPORT_ID/decision" `
  -H "Authorization: Bearer local-reviewer-token" `
  -H "Content-Type: application/json" `
  -d "@approve-request.json"
```

Conceptually:

```json
{
  "version": 1,
  "decision": "approved",
  "comment": "Evidence reviewed and approved."
}
```

Reject uses:

```json
{
  "version": 1,
  "decision": "rejected",
  "comment": "Please revise the unsupported finding."
}
```

Use `/docs` for the exact runtime schema.

---

# 33. Export Approved Report

Example:

```powershell
curl.exe "http://127.0.0.1:8000/reports/YOUR_REPORT_ID/export?version=1" `
  -H "Authorization: Bearer local-analyst-token"
```

Only an approved immutable version is eligible.

Draft, pending, rejected, or stale unapproved content is refused.

---

# 34. Keyless Replay Mode

The full backend can be exercised without a live model by using replay execution.

Replay mode supports:

- import;
- analysis mechanics;
- persistence;
- deterministic scoring;
- failures;
- result retrieval;
- report creation;
- editing;
- submission;
- review;
- export;
- evaluation infrastructure.

Replay is explicitly labelled as replay.

It is not treated as an independent live-model quality measurement.

---

# 35. Real Model Mode

For live semantic analysis, configure:

```env
LLM_API_KEY=your-approved-key
LLM_MODEL=your-approved-model
```

Do not place credentials in source code.

The model adapter is responsible only for semantic interpretation.

All scoring, evidence validation, and workflow authorization remain deterministic.

---

# 36. Automated Tests

Run:

```powershell
pytest -q
```

Final verified result:

```text
........................
24 passed
```

The software tests cover required backend behavior.

Analysis tests include:

1. all responses accounted for;
2. empty response skipped rather than scored zero;
3. matching configuration reuses an analysis run;
4. rerun does not duplicate results;
5. successful results are not reprocessed;
6. replay labels are persisted;
7. failed analysis is not converted to zero;
8. analysis summary API;
9. status filtering;
10. engine filtering;
11. pagination;
12. unknown analysis returns 404.

Report/review tests include:

1. analyst create/edit/submit;
2. reviewer cannot create an analyst report;
3. analyst cannot approve;
4. reviewer can approve;
5. repeated decision is rejected;
6. expired review is rejected;
7. submitted/unapproved version cannot export;
8. approved version can export;
9. editing after approval creates a new draft;
10. approved older version remains exportable;
11. stale edit is rejected;
12. rejected version cannot export.

These are software correctness tests and are intentionally separate from semantic model-quality evaluation.

---

# 37. Evaluation Harness

Run the complete evaluation with:

```powershell
python -m evaluation.grader
```

The evaluation contains:

```text
Gold fixture      : gold-v1
Synthetic fixture : synthetic-v1

Gold cases        : 15
Synthetic cases   : 6
```

The gold cases are manually labelled supplied responses.

Distribution:

```text
AI Mode : 5
ChatGPT : 5
Gemini  : 5
```

Prompt categories:

```text
Branded   : 9
Discovery : 6
```

This exceeds the minimum requirement of 12 supplied responses and spans all three engines and multiple prompt categories.

---

# 38. Live Gold-Set Evaluation

Persisted live analysis:

```text
analysis:2f8298d6-d3d0-4ed7-a201-089369d1e273
```

Gold-set results:

```text
Cases                  : 15
Successfully evaluated : 14
Non-success            : 1
Missing                : 0
Coverage               : 93.3%

Exact agreement        : 11 / 14
Exact agreement rate   : 78.6%
```

Per-label results:

| Label | Precision | Recall | Agreement |
|---|---:|---:|---:|
| Mentioned | 1.000 | 1.000 | 1.000 |
| Recommended | 0.500 | 1.000 | 0.786 |
| Negative | 1.000 | 0.750 | 0.929 |

The largest semantic weakness is recommendation over-classification.

The live model detected all expected recommendation cases but also classified three additional successful gold cases as recommendations.

This result is reported rather than hidden.

---

# 39. Deterministic Replay Baseline

The same gold cases are evaluated using the deterministic replay baseline.

Result:

```text
Exact agreement : 9 / 15
Agreement rate  : 60.0%
```

Per-label baseline results:

| Label | Precision | Recall | Agreement |
|---|---:|---:|---:|
| Mentioned | 1.000 | 1.000 | 1.000 |
| Recommended | 1.000 | 0.000 | 0.800 |
| Negative | 1.000 | 0.250 | 0.800 |

The replay baseline handles literal brand mention well but misses semantic recommendation and negative-characterization cases.

Because one live gold case was a non-success, the 60.0% and 78.6% figures are not treated as a perfectly matched statistical benchmark. They are used to demonstrate the value and limitations of semantic interpretation.

---

# 40. Deterministic Score Verification

The evaluation independently verifies score calculations.

Result:

```text
9 / 9 passed
```

Cases include:

```text
absent
mention_only
recommendation
position_1
position_2
position_3
mention_with_citation
negative_mention
maximum_score
```

This verifies that semantic interpretation and score calculation remain separate concerns.

---

# 41. Model Output Validation Evaluation

Validation checks:

```text
4 / 4 passed
```

The cases verify:

- valid evidence is accepted;
- unsupported evidence is rejected;
- recommendation without mention is rejected;
- recommendation position without recommendation is rejected.

This includes an incorrect/unsupported-evidence case.

---

# 42. Synthetic Edge Cases

Synthetic fixture:

```text
synthetic-v1
```

Result:

```text
6 / 6 passed
```

Cases cover:

- empty response;
- mention;
- negative characterization;
- recommendation;
- absence;
- unsupported evidence.

Synthetic cases are clearly separated from the manually labelled supplied-response gold set.

---

# 43. Live Model Repeatability

Five fixed gold cases were executed twice using the same live configuration.

This produced:

```text
Cases             : 5
Runs per case     : 2
Total calls       : 10
Successful calls  : 7 / 10
Comparable pairs  : 3 / 5
Exact agreement   : 3 / 3 comparable pairs
Average latency   : 7.938 seconds
Median latency    : 7.666 seconds
Cost measurement : Unavailable from the adapter
```

Per-case observations:

```text
gold-001  AI Mode   T/F/T -> T/F/T       exact pair
gold-002  AI Mode   T/T/F -> T/T/F       exact pair
gold-003  AI Mode   T/T/T -> invalid     one failed run
gold-004  ChatGPT   T/T/F -> T/T/F       exact pair
gold-005  ChatGPT   invalid -> invalid   two failed runs
```

The three comparable successful pairs produced identical semantic labels.

However, 3 of the 10 fresh calls failed strict structured-output/evidence validation.

This indicates that the semantic classifications were stable across the comparable valid pairs while structured-output/evidence reliability remains an execution weakness.

Per-request monetary cost was not available from the adapter and is therefore reported as unavailable rather than zero.

---

# 44. Full Dataset Results

Final live run:

```text
Total     : 150
Success   : 148
Failed    : 2
Skipped   : 0
Accounted : 150

Coverage  : 98.7%
```

Every supplied response has a terminal result.

Failures remain failures.

They are not manufactured into confident zero scores.

---

# 45. Overall Results

Across the 148 successfully analyzed responses:

```text
Mentioned   : 70 / 148 = 47.3%
Recommended : 19 / 148 = 12.8%
Negative    : 25 / 148 = 16.9%

Average visibility score: 17.2
```

However, these aggregate results mix branded and unbranded prompts.

They should **not** be interpreted as Kasparro's organic AI visibility.

Prompt-category segmentation is necessary.

---

# 46. Branded Prompts

For prompts explicitly involving Kasparro:

```text
Eligible    : 75
Successful  : 73

Mentioned   : 70 / 73 = 95.9%
Recommended : 19 / 73 = 26.0%
Negative    : 25 / 73 = 34.2%

Average score: 34.9
```

Kasparro therefore has strong recognition when the brand is explicitly introduced into the prompt.

Recognition does not automatically translate into recommendation.

---

# 47. Discovery Prompts

For unbranded discovery prompts:

```text
Eligible    : 75
Successful  : 75

Mentioned   : 0 / 75
Recommended : 0 / 75
Negative    : 0 / 75

Average score: 0
```

This is the most important observed loss in the supplied snapshot.

> **Kasparro was recognized when explicitly prompted but did not appear organically in any of the 75 successfully analyzed unbranded discovery responses.**

This statement describes the supplied archived snapshot only.

It is not a claim about current AI-engine behavior.

---

# 48. Engine Comparison — Branded Prompts

## Google AI Mode

```text
Successful   : 24 / 25
Mentioned    : 100.0%
Recommended  : 25.0%
Negative     : 33.3%
Average score: 34.2
```

## ChatGPT

```text
Successful   : 25 / 25
Mentioned    : 100.0%
Recommended  : 24.0%
Negative     : 56.0%
Average score: 29.6
```

## Gemini

```text
Successful   : 24 / 25
Mentioned    : 87.5%
Recommended  : 29.2%
Negative     : 12.5%
Average score: 41.2
```

These results compare the archived supplied responses and should not be interpreted as universal provider rankings.

---

# 49. Diagnostic 1 — Organic Discovery Gap

## Recorded pattern

Kasparro appeared in:

```text
0 / 75
```

successfully analyzed discovery responses.

## Possible explanation

The supplied snapshot suggests that Kasparro has much stronger explicit-brand recognition than organic category inclusion.

This does not establish the cause.

## Evidence to test

Inspect recurring competitors and source domains across the same discovery prompts.

Repeat the same discovery prompt set after investigating independent category references and authority signals.

Keep the prompt set, category version, and scoring version constant where possible.

---

# 50. Diagnostic 2 — Recognition Does Not Consistently Become Recommendation

Successful branded responses:

```text
Mentioned   : 70 / 73
Recommended : 19 / 73
```

## Recorded pattern

Kasparro is usually recognized when explicitly named but is substantially less often presented as a recommended option.

## Possible explanation

The available evidence may establish brand existence more strongly than comparative suitability.

## Evidence to test

Inspect paired examples where Kasparro is:

- mentioned but not recommended;
- explicitly recommended.

Compare trust signals, comparative claims, source support, and recommendation language.

---

# 51. Diagnostic 3 — Negative Characterization Varies by Engine

Successful branded responses:

```text
ChatGPT : 14 / 25 = 56.0%
AI Mode :  8 / 24 = 33.3%
Gemini  :  3 / 24 = 12.5%
```

## Recorded pattern

Negative characterization differs substantially across the three archived surfaces.

## Possible explanation

Different engines may retrieve or emphasize different evidence or describe limitations differently.

The dataset alone does not prove that explanation.

## Evidence to test

Cluster the exact negative claims and inspect:

- response excerpts;
- supplied citations;
- likely supporting sources;
- repeated themes across engines.

---

# 52. Remedy 1 — Investigate Category-Level Authority and Discovery Visibility

**Priority:** 1

## Problem

Kasparro appeared in none of the 75 successfully analyzed unbranded discovery responses.

## Evidence

The discovery subset produced:

```text
Mentioned   : 0 / 75
Recommended : 0 / 75
```

## Action

Map recurring competitors and cited domains for the same discovery prompts, then identify evidence gaps Kasparro can substantively address.

Potential areas to investigate include:

- evidence-backed category content;
- independent references;
- comparative material;
- externally verifiable descriptions of Kasparro's role in the category.

## Expected benefit

Produce a defensible explanation of the observed discovery gap and identify evidence that may improve category association.

## Effort

Medium to high.

## Uncertainty

High until source-level comparison is completed.

Retrieval and ranking behavior varies across systems and over time.

No ranking improvement is promised.

## Validation

Repeat the same discovery prompt set after evidence-backed changes and compare inclusion using the same category and scoring versions.

---

# 53. Remedy 2 — Strengthen Recommendation-Oriented Evidence

**Priority:** 2

## Problem

Kasparro is mentioned much more often than it is recommended in successful branded responses.

```text
Mentioned   : 70 / 73
Recommended : 19 / 73
```

## Action

Investigate which verifiable proof points distinguish recommended providers, including:

- comparative proof;
- independent validation;
- relevant case studies;
- clearly supported differentiators;
- trust signals;
- evidence demonstrating suitability for specific use cases.

## Expected benefit

Improve understanding of the gap between brand recognition and recommendation.

## Effort

Medium to high.

## Uncertainty

Recommendation behavior differs by engine, and recommendation classification itself has measured uncertainty.

## Validation

Repeat the same branded prompts and track recommendation separately from mention.

---

# 54. Remedy 3 — Investigate Negative Themes

**Priority:** 3

## Problem

25 of 73 successfully analyzed branded responses contained negative characterization.

The rate varies substantially by engine.

## Action

Cluster negative claims and trace supplied citations where available.

Determine whether recurring claims are:

- accurate;
- stale;
- unsupported;
- product-related;
- content-related;
- or not actionable.

## Expected benefit

Prioritize factual issues rather than speculative ranking tactics.

## Effort

Low to medium.

## Uncertainty

Medium.

Negative statements may derive from historical, incomplete, or changing external material.

## Validation

Maintain a dated claim/source register and repeat affected prompts after evidence-backed corrections.

---

# 55. Failure → Diagnosis → Change → Regression Protection

A real failure was observed during live execution.

## Failure

Initial live execution reached:

```text
141 / 150 successful
9 failures
```

## Diagnosis

Several failures were caused by model-generated evidence that did not satisfy exact evidence validation.

## Decision

Evidence validation was not relaxed.

Allowing approximate or unsupported evidence would weaken auditability.

## Change

Invalid model output was made retryable under the existing bounded retry policy.

The same persisted analysis was resumed.

## Result

```text
148 / 150 successful
2 explicit failures
```

## Regression protection

Tests and evaluation cover:

- successful-result reuse;
- duplicate-result prevention;
- failure accounting;
- unsupported evidence;
- model-output validation;
- resumable execution.

The remaining failures were preserved rather than hidden.

---

# 56. Evaluation Limitations

The gold set is intentionally small.

Fifteen manually labelled responses are sufficient for the assignment requirement but are not enough to claim broad statistical model quality.

The evaluation also shows that recommendation classification remains imperfect.

The grader therefore reports separate label metrics rather than relying only on one aggregate accuracy number.

An LLM is not used as the sole judge of its own prose.

Expected labels and deterministic checks are stored separately.

The live repeatability experiment is also deliberately small.

Three of ten fresh live calls failed strict structured-output/evidence validation, so the 3/3 comparable-pair agreement should not be interpreted as evidence of universal model stability.

---

# 57. Security and Trust Boundaries

Source prompts and answers are treated as untrusted data.

They cannot:

- change application permissions;
- assign reviewer identity;
- approve a report;
- enable export;
- override scoring logic.

Secrets are loaded from environment variables.

The repository should not commit:

```text
.env
.venv/
__pycache__/
*.pyc
*.db
.pytest_cache/
data/
provenance/
```

Supplied/private data should not be placed into public Git history.

---

# 58. `.gitignore`

Recommended entries:

```gitignore
.venv/
__pycache__/
*.pyc
*.db
.env
.pytest_cache/
data/
provenance/
```

This keeps local secrets, generated databases, caches, and supplied/private source material out of Git history.

---

# 59. Deliberate Omissions

The following were deliberately not added:

- dashboard;
- Docker;
- Kubernetes;
- Redis;
- Celery;
- vector database;
- crawling;
- public deployment;
- multiple agents.

These features do not materially improve the correctness of this assignment's 150-response archived workload.

The implementation instead prioritizes:

- correctness;
- transparent scoring;
- evidence traceability;
- failure visibility;
- idempotency;
- restart/resume behavior;
- evaluation;
- human review;
- version-safe export.

---

# 60. Production Alternatives

For a larger production deployment, I would consider:

## PostgreSQL

Replace SQLite for stronger multi-worker transactional behavior.

## Background workers

Introduce asynchronous execution if model-call latency or workload makes synchronous processing inappropriate.

## Production identity

Replace local bearer tokens with an identity provider and role-based access control.

## Observability

Add structured telemetry for:

- model latency;
- token usage;
- provider cost;
- retries;
- validation failures;
- run coverage;
- state transitions.

## Expanded evaluation

Increase manually labelled cases and maintain a larger frozen regression set.

---

# 61. Largest Current Risk

The largest current risk is semantic classification quality, especially the distinction between:

```text
positive mention
```

and:

```text
recommendation
```

The live gold evaluation measured recommendation precision at:

```text
0.500
```

with recall:

```text
1.000
```

The next semantic iteration would therefore tighten the recommendation rubric and add hard-negative examples such as:

- neutral comparisons;
- weak consideration language;
- statements that merely list Kasparro as an available option.

A second observed reliability risk is structured-output/evidence validity: 3 of 10 calls in the small live-repeatability experiment failed strict validation.

These weaknesses are intentionally visible rather than tuned away against the final evaluation set.

---

# 62. Questions Before Production Release

Before production use, I would clarify:

1. What exact product definition distinguishes recommendation from positive mention?
2. Are the current visibility-score weights business-approved or only explanatory?
3. What review-expiry duration and escalation policy should apply?
4. What model latency and cost budgets are acceptable?
5. What retention requirements apply to archived provider payloads?
6. What access controls are required for customer datasets?
7. Should citation presence contribute to score before citation support is independently verified?
8. How frequently should prompt/category definitions be versioned and refreshed?

---

# 63. AI Assistance Disclosure

AI coding assistance was used during the assignment for:

- architecture discussion;
- code drafting;
- debugging;
- test design;
- evaluation design;
- documentation;
- review.

Generated suggestions were not treated as automatically correct.

The implementation was verified through:

- direct execution;
- source inspection;
- automated software tests;
- deterministic score checks;
- model-output validation;
- manually labelled evaluation cases;
- controlled synthetic cases;
- live repeatability measurements.

The final automated backend test suite passes:

```text
24 / 24
```

Software correctness and semantic model quality are reported separately.

---

# 64. Active Time

**Actual active time: approximately 5 hours.**

This includes active time spent on:

- reviewing the supplied requirements and dataset;
- backend and persistence implementation;
- semantic-analysis and deterministic-scoring implementation;
- human-review/version workflow;
- debugging and automated testing;
- evaluation and analysis;
- documentation and final verification.

Breaks, inactive waiting time, and unrelated activity were excluded.

The implementation was intentionally scoped to the assignment's six-active-hour constraint. Optional infrastructure and additional model-quality iteration were omitted in favor of correctness, traceability, evaluation, and human review.

---

# 65. Final Verification Summary

```text
BACKEND
-------
FastAPI backend                  PASS
SQLite persistence               PASS
Raw input preservation           PASS
Analysis persistence             PASS
Report persistence               PASS
Review persistence               PASS
Health endpoint                  PASS
Generated API documentation      PASS

ANALYSIS
--------
150 responses                    ACCOUNTED
148 success
2 failed
0 skipped
98.7% successful coverage

SEMANTIC CLASSIFICATION
-----------------------
Mention                          IMPLEMENTED
Recommendation                   IMPLEMENTED
Negative characterization        IMPLEMENTED
Competitors                      IMPLEMENTED
Recommendation position          IMPLEMENTED
Evidence excerpts                IMPLEMENTED

SCORING
-------
Transparent score                PASS
Versioned scoring                PASS
Failed != zero                   PASS
Score verification               9 / 9

RELIABILITY
-----------
Bounded retries                  PASS
Resume                           PASS
Idempotent completed results     PASS
Configuration identity           PASS
Failure preservation             PASS
Pagination                       PASS
Stale edit protection            PASS
Repeated decision protection     PASS

HUMAN REVIEW
------------
Analyst/reviewer separation      PASS
Immutable submission             PASS
Approval                         PASS
Rejection                        PASS
Review expiry                    PASS
Version-safe export              PASS
Old approved export              PASS

SOFTWARE TESTS
--------------
24 / 24 passed

EVALUATION
----------
Gold supplied cases              15
Successfully evaluated           14 / 15
Synthetic cases                  6
All three engines                YES
Multiple categories              YES

Live exact agreement             11 / 14 = 78.6%
Replay exact agreement           9 / 15 = 60.0%

Mention precision/recall         1.000 / 1.000
Recommendation precision/recall  0.500 / 1.000
Negative precision/recall        1.000 / 0.750

Validation checks                4 / 4
Synthetic checks                 6 / 6
Score checks                     9 / 9

LIVE REPEATABILITY
------------------
Cases                            5
Runs per case                    2
Total live calls                 10
Successful calls                 7 / 10
Comparable pairs                 3 / 5
Exact comparable-pair agreement  3 / 3
Average latency                  7.938 seconds
Median latency                   7.666 seconds
Cost measurement                 Unavailable

DOCUMENTATION
-------------
README                           COMPLETE
Decision note                    INCLUDED SEPARATELY
Analysis output                  INCLUDED
Evaluation results               INCLUDED
AI assistance disclosure         INCLUDED
Deliberate omissions             INCLUDED
Exactly-once limitation          INCLUDED
Active-time disclosure           INCLUDED
```

---

# 66. Final Result

The implementation demonstrates a complete flow from archived AI responses to evidence-grounded semantic analysis, deterministic scoring, diagnostics, remedies, human review, and version-safe export.

The central engineering decision remains:

> **AI interprets. Code decides.**

Semantic models are used where language understanding provides value.

Deterministic software remains responsible for validation, scoring, accounting, persistence, permissions, versioning, and export safety.

That separation makes model uncertainty visible while keeping the backend auditable and predictable.
