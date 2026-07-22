# Evaluation Run Evidence — `2026-07-22-01-08-00-5144`

> **Timestamp (UTC)**: `2026-07-21T18:08:00.514377+00:00`  
> **Git SHA**: `4b085f7ce6a365a7196fd8c6fdb34b62c81c4d88`  
> **Model ID**: `us.amazon.nova-2-lite-v1:0`  
> **Environment**: `local`  
> **Config Source**: `env_override`

## 1. System Snapshots & Hashes

- **Database SHA-256 (`init.sql`)**: `7f7259b5e2b95e2c8c534fdc53c56a4ec7e9ce26e99a6b37adddaf9747de77d1`
- **Dataset SHA-256**: `e9210245c74f5850ac85253bda6896790b88e2372b4f0600caeb0bcb3e19f19c`
- **Dataset File Path**: [eval_dataset.json](../../eval_dataset.json)
- **Snapshot Folder**: [`snapshots/`](snapshots/)
  - [`manifest.json`](snapshots/manifest.json) — Commit hash, model details, config source flag
  - [`system_prompt.txt`](snapshots/system_prompt.txt) — Exact Bedrock search intent system prompt
  - [`config.yaml`](snapshots/config.yaml) — Whitelist schemas, thresholds, guardrail rules
  - [`eval_summary.json`](snapshots/eval_summary.json) — Faithfulness rate, injection block rate, token & cost totals

## 2. Rerun Command

To reproduce this evaluation run exact setup, execute:
```bash
python3 tests/eval_natural_language_product_search_mvp/run_eval.py --port 32960 --runtime-env local
```

## 3. Quick Summary of Results

| Metric | Value |
| :--- | :--- |
| **Total Cases** | `7` |
| **Passed Cases** | `6` |
| **Failed Cases** | `1` |
| **Pass Rate** | **85.7%** |
| **Faithfulness Rate (`return_products`)** | `0.767` |
| **Avg Recall (`return_products`)** | `1.000` |
| **Total Input Tokens** | `12,247` |
| **Total Output Tokens** | `577` |
| **Total Estimated Cost (USD)** | `$0.005117` |

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
| `TC-01` | `vietnamese_nlp` | *"có những loại kính thiên văn nào?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `1YMWWN1N4O, 66VCHSJNUP, OLJCESPC7Z` | `False` | 1.00 | 1.00 | `1752` | `102` | `$0.000781` | **✅ PASS** |
| `TC-02` | `vietnamese_nlp` | *"đèn pin"* | `LS4PSXUNUM` | `LS4PSXUNUM` | `False` | 1.00 | 1.00 | `1747` | `84` | `$0.000734` | **✅ PASS** |
| `TC-03` | `vietnamese_nlp` | *"có kính thiên văn nào rẻ rẻ không?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `1753` | `105` | `$0.000788` | **✅ PASS** |
| `TC-04` | `vietnamese_nlp` | *"màn lọc kính thiên văn"* | `6E92ZMYYFZ` | `0PUK6V6EV0, 6E92ZMYYFZ` | `False` | 0.50 | 1.00 | `1750` | `89` | `$0.000748` | **✅ PASS** |
| `TC-05` | `vietnamese_nlp` | *"chòa bạn"* | `[]` | `[]` | `True` | — | — | `1747` | `53` | `$0.000657` | **✅ PASS** |
| `TC-06` | `vietnamese_nlp` | *"tôi muốn mua kính thiên văn rẻ nhất"* | `OLJCESPC7Z` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 0.33 | 1.00 | `1753` | `91` | `$0.000753` | **❌ FAIL** |
| `TC-07` | `vietnamese_nlp` | *"hi"* | `[]` | `[]` | `True` | — | — | `1745` | `53` | `$0.000656` | **✅ PASS** |
