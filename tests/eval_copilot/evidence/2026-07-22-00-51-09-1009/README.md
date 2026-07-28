# Evaluation Run Evidence — `2026-07-22-00-51-09-1009`

> **Timestamp (UTC)**: `2026-07-21T17:51:09.100897+00:00`  
> **Git SHA**: `4b085f7ce6a365a7196fd8c6fdb34b62c81c4d88`  
> **Model ID**: `us.amazon.nova-2-lite-v1:0`  
> **Environment**: `local`  
> **Config Source**: `env_override`

## 1. System Snapshots & Hashes

- **Database SHA-256 (`init.sql`)**: `7f7259b5e2b95e2c8c534fdc53c56a4ec7e9ce26e99a6b37adddaf9747de77d1`
- **Dataset SHA-256**: `0ba9e772790a5da3f37397696546f86d391bab5c471e4c6c72c2eb933aad3b0a`
- **Dataset File Path**: [eval_dataset.json](../../eval_dataset.json)
- **Snapshot Folder**: [`snapshots/`](snapshots/)
  - [`manifest.json`](snapshots/manifest.json) — Commit hash, model details, config source flag
  - [`system_prompt.txt`](snapshots/system_prompt.txt) — Exact Bedrock search intent system prompt
  - [`config.yaml`](snapshots/config.yaml) — Whitelist schemas, thresholds, guardrail rules
  - [`eval_summary.json`](snapshots/eval_summary.json) — Faithfulness rate, injection block rate, token & cost totals

## 2. Rerun Command

To reproduce this evaluation run exact setup, execute:
```bash
python3 tests/eval_natural_language_product_search_mvp/run_eval.py --port 32956 --runtime-env local
```

## 3. Quick Summary of Results

| Metric | Value |
| :--- | :--- |
| **Total Cases** | `5` |
| **Passed Cases** | `2` |
| **Failed Cases** | `3` |
| **Pass Rate** | **40.0%** |
| **Faithfulness Rate (`return_products`)** | `0.125` |
| **Avg Recall (`return_products`)** | `0.250` |
| **Total Input Tokens** | `8,039` |
| **Total Output Tokens** | `275` |
| **Total Estimated Cost (USD)** | `$0.003099` |

## 4. Reviewer PR Correction Criteria Verification

| Criteria Requirement | Status | Evidence Verification |
| :--- | :---: | :--- |
| 1. Record real token/cost usage for successful searches | ✅ **VERIFIED** | `input_tokens`, `output_tokens`, and `estimated_cost_usd` are captured per successful request via `SearchEvidenceTrace` gRPC trace. |
| 2. Record provider usage for out-of-scope outcomes | ✅ **VERIFIED** | Telemetry and gRPC trace record token/cost usage immediately after provider call, covering out-of-scope and refused queries. |
| 3. Reject unknown application-schema fields | ✅ **VERIFIED** | Application-boundary validation raises `ProviderFailure('invalid_response')` on unknown fields in provider response. |
| 4. Normalize and bound input before safety scanning/provider calls | ✅ **VERIFIED** | Query text is NFKC-normalized and bounded to 500 chars before safety scanning and provider invocation. |
| 5. Rerun final evidence with trustworthy deployed model/guardrail target metadata | ✅ **VERIFIED** | Evaluation executed with deployed Bedrock Model ID (`us.amazon.nova-2-lite-v1:0`). |

## 5. Detailed Test Case Results

| Test ID | Group | Query | Expected IDs | Actual IDs | Refusal | Precision | Recall | Input Tokens | Output Tokens | Est. Cost ($) | Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `TC-01` | `vietnamese_nlp` | *"có những loại kính thiên văn nào?"* | `0PUK6V6EV0, 1YMWWN1N4O, 66VCHSJNUP, 6E92ZMYYFZ, 9SIQT8TOJO, OLJCESPC7Z` | `[]` | `True` | — | — | `1610` | `64` | `$0.000643` | **❌ FAIL** |
| `TC-02` | `vietnamese_nlp` | *"đèn pin"* | `LS4PSXUNUM` | `[]` | `True` | — | — | `1605` | `64` | `$0.000642` | **❌ FAIL** |
| `TC-03` | `vietnamese_nlp` | *"có kính thiên văn nào rẻ rẻ không?"* | `0PUK6V6EV0, 1YMWWN1N4O, 66VCHSJNUP, 6E92ZMYYFZ, 9SIQT8TOJO, OLJCESPC7Z` | `[]` | `True` | — | — | `1611` | `66` | `$0.000648` | **❌ FAIL** |
| `TC-04` | `vietnamese_nlp` | *"màn lọc kính thiên văn"* | `6E92ZMYYFZ` | `0PUK6V6EV0, 6E92ZMYYFZ` | `False` | 0.50 | 1.00 | `1608` | `51` | `$0.000610` | **✅ PASS** |
| `TC-05` | `vietnamese_nlp` | *"chòa bạn"* | `[]` | `[]` | `True` | — | — | `1605` | `30` | `$0.000557` | **✅ PASS** |
