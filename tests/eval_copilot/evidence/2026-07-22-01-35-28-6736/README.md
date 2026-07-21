# Evaluation Run Evidence — `2026-07-22-01-35-28-6736`

> **Timestamp (UTC)**: `2026-07-21T18:35:28.673604+00:00`  
> **Git SHA**: `c1e9a317f2231bb99019f93fb5831deefe7771dd`  
> **Model ID**: `us.amazon.nova-2-lite-v1:0`  
> **Environment**: `local`  
> **Config Source**: `env_override`

## 1. System Snapshots & Hashes

- **Database SHA-256 (`init.sql`)**: `7f7259b5e2b95e2c8c534fdc53c56a4ec7e9ce26e99a6b37adddaf9747de77d1`
- **Dataset SHA-256**: `d465e26f9e09d200ebfe254d427214c8d8e3b38d4107472e4d58f8ffe7f96f0b`
- **Dataset File Path**: [eval_dataset.json](../../eval_dataset.json)
- **Snapshot Folder**: [`snapshots/`](snapshots/)
  - [`manifest.json`](snapshots/manifest.json) — Commit hash, model details, config source flag
  - [`system_prompt.txt`](snapshots/system_prompt.txt) — Exact Bedrock search intent system prompt
  - [`config.yaml`](snapshots/config.yaml) — Whitelist schemas, thresholds, guardrail rules
  - [`eval_summary.json`](snapshots/eval_summary.json) — Faithfulness rate, injection block rate, token & cost totals

## 2. Rerun Command

To reproduce this evaluation run exact setup, execute:
```bash
python3 tests/eval_natural_language_product_search_mvp/run_eval.py --port 32969 --runtime-env local
```

## 3. Quick Summary of Results

| Metric | Value |
| :--- | :--- |
| **Total Cases** | `11` |
| **Passed Cases** | `9` |
| **Failed Cases** | `2` |
| **Pass Rate** | **81.8%** |
| **Faithfulness Rate (`return_products`)** | `0.688` |
| **Avg Recall (`return_products`)** | `0.750` |
| **Total Input Tokens** | `23,405` |
| **Total Output Tokens** | `1,341` |
| **Total Estimated Cost (USD)** | `$0.010374` |

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
| `TC-01` | `vietnamese_nlp` | *"có những loại kính thiên văn nào?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `1YMWWN1N4O, 66VCHSJNUP, OLJCESPC7Z` | `False` | 1.00 | 1.00 | `1994` | `109` | `$0.000871` | **✅ PASS** |
| `TC-02` | `vietnamese_nlp` | *"đèn pin"* | `LS4PSXUNUM` | `LS4PSXUNUM` | `False` | 1.00 | 1.00 | `1989` | `84` | `$0.000807` | **✅ PASS** |
| `TC-03` | `vietnamese_nlp` | *"có kính thiên văn nào rẻ rẻ không?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `1995` | `101` | `$0.000851` | **✅ PASS** |
| `TC-04` | `vietnamese_nlp` | *"màn lọc kính thiên văn"* | `6E92ZMYYFZ` | `0PUK6V6EV0, 6E92ZMYYFZ` | `False` | 0.50 | 1.00 | `1992` | `89` | `$0.000820` | **✅ PASS** |
| `TC-05` | `vietnamese_nlp` | *"chòa bạn"* | `[]` | `[]` | `True` | — | — | `1989` | `53` | `$0.000729` | **✅ PASS** |
| `TC-06` | `vietnamese_nlp` | *"tôi muốn mua kính thiên văn rẻ nhất"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `1995` | `105` | `$0.000861` | **✅ PASS** |
| `TC-07` | `vietnamese_nlp` | *"hi"* | `[]` | `[]` | `True` | — | — | `1987` | `53` | `$0.000729` | **✅ PASS** |
| `TC-08` | `vietnamese_nlp` | *"có truyện tranh không?"* | `HQTGWGPNH4` | `HQTGWGPNH4` | `False` | 1.00 | 1.00 | `1992` | `76` | `$0.000788` | **✅ PASS** |
| `TC-09` | `vietnamese_nlp` | *"tôi muốn mua 1 bộ one piece"* | `[]` | `[]` | `True` | — | — | `1995` | `149` | `$0.000971` | **✅ PASS** |
| `TC-10` | `vietnamese_nlp` | *"thêm cái đắt nhất vào giỏ hàng"* | `66VCHSJNUP` | `66VCHSJNUP, 1YMWWN1N4O` | `True` | — | — | `2032` | `102` | `$0.000865` | **❌ FAIL** |
| `TC-11` | `vietnamese_nlp` | *"đánh giá như thế nào?"* | `1YMWWN1N4O` | `2ZYFJ3GM2N` | `False` | 0.00 | 0.00 | `3445` | `420` | `$0.002083` | **❌ FAIL** |
