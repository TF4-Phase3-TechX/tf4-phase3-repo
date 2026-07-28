# Evaluation Run Evidence — `2026-07-22-01-55-17-0100`

> **Timestamp (UTC)**: `2026-07-21T18:55:17.010049+00:00`  
> **Git SHA**: `12d21e20a30b405c791bc19e3d09d9531ce69b83`  
> **Model ID**: `us.amazon.nova-2-lite-v1:0`  
> **Environment**: `local`  
> **Config Source**: `env_override`

## 1. System Snapshots & Hashes

- **Database SHA-256 (`init.sql`)**: `7f7259b5e2b95e2c8c534fdc53c56a4ec7e9ce26e99a6b37adddaf9747de77d1`
- **Dataset SHA-256**: `600bb09fc4cac356ecd62d80c2d66d6422d3b94d20bb962c131929dd5abfc868`
- **Dataset File Path**: [eval_dataset.json](../../eval_dataset.json)
- **Snapshot Folder**: [`snapshots/`](snapshots/)
  - [`manifest.json`](snapshots/manifest.json) — Commit hash, model details, config source flag
  - [`system_prompt.txt`](snapshots/system_prompt.txt) — Exact Bedrock search intent system prompt
  - [`config.yaml`](snapshots/config.yaml) — Whitelist schemas, thresholds, guardrail rules
  - [`eval_summary.json`](snapshots/eval_summary.json) — Faithfulness rate, injection block rate, token & cost totals

## 2. Rerun Command

To reproduce this evaluation run exact setup, execute:
```bash
python3 tests/eval_natural_language_product_search_mvp/run_eval.py --port 32973 --runtime-env local
```

## 3. Quick Summary of Results

| Metric | Value |
| :--- | :--- |
| **Total Cases** | `12` |
| **Passed Cases** | `11` |
| **Failed Cases** | `1` |
| **Pass Rate** | **91.7%** |
| **Faithfulness Rate (`return_products`)** | `0.833` |
| **Avg Recall (`return_products`)** | `0.889` |
| **Total Input Tokens** | `24,024` |
| **Total Output Tokens** | `1,344` |
| **Total Estimated Cost (USD)** | `$0.010567` |

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
| `TC-01` | `vietnamese_nlp` | *"có những loại kính thiên văn nào?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `1YMWWN1N4O, 66VCHSJNUP, OLJCESPC7Z` | `False` | 1.00 | 1.00 | `2044` | `126` | `$0.000928` | **✅ PASS** |
| `TC-02` | `vietnamese_nlp` | *"đèn pin"* | `LS4PSXUNUM` | `LS4PSXUNUM` | `False` | 1.00 | 1.00 | `2039` | `84` | `$0.000822` | **✅ PASS** |
| `TC-03` | `vietnamese_nlp` | *"có kính thiên văn nào rẻ rẻ không?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `2045` | `105` | `$0.000876` | **✅ PASS** |
| `TC-04` | `vietnamese_nlp` | *"màn lọc kính thiên văn"* | `6E92ZMYYFZ` | `0PUK6V6EV0, 6E92ZMYYFZ` | `False` | 0.50 | 1.00 | `2042` | `92` | `$0.000843` | **✅ PASS** |
| `TC-05` | `vietnamese_nlp` | *"chòa bạn"* | `[]` | `[]` | `True` | — | — | `2039` | `53` | `$0.000744` | **✅ PASS** |
| `TC-06` | `vietnamese_nlp` | *"tôi muốn mua kính thiên văn rẻ nhất"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `2045` | `105` | `$0.000876` | **✅ PASS** |
| `TC-07` | `vietnamese_nlp` | *"hi"* | `[]` | `[]` | `True` | — | — | `2037` | `53` | `$0.000744` | **✅ PASS** |
| `TC-08` | `vietnamese_nlp` | *"có truyện tranh không?"* | `HQTGWGPNH4` | `HQTGWGPNH4` | `False` | 1.00 | 1.00 | `2042` | `90` | `$0.000838` | **✅ PASS** |
| `TC-09` | `vietnamese_nlp` | *"tôi muốn mua 1 bộ one piece"* | `[]` | `[]` | `True` | — | — | `2045` | `83` | `$0.000821` | **✅ PASS** |
| `TC-10` | `vietnamese_nlp_multiturn` | *"thêm cái đắt nhất vào giỏ hàng"* | `66VCHSJNUP` | `66VCHSJNUP` | `False` | 1.00 | 1.00 | `2125` | `87` | `$0.000855` | **✅ PASS** |
| `TC-11` | `vietnamese_nlp_multiturn` | *"đánh giá như thế nào?"* | `2ZYFJ3GM2N` | `2ZYFJ3GM2N` | `False` | 1.00 | 1.00 | `3521` | `466` | `$0.002221` | **✅ PASS** |
| `TC-12` | `vietnamese_nlp_multiturn` | *"cái nào rẻ nhất"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `[]` | `True` | — | — | `0` | `0` | `$0.000000` | **❌ FAIL** |
