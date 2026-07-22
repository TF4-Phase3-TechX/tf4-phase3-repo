# Evaluation Run Evidence — `2026-07-22-01-18-08-2944`

> **Timestamp (UTC)**: `2026-07-21T18:18:08.294383+00:00`  
> **Git SHA**: `6006936ccfd319af6657b2342786d80f40cd0414`  
> **Model ID**: `us.amazon.nova-2-lite-v1:0`  
> **Environment**: `local`  
> **Config Source**: `env_override`

## 1. System Snapshots & Hashes

- **Database SHA-256 (`init.sql`)**: `7f7259b5e2b95e2c8c534fdc53c56a4ec7e9ce26e99a6b37adddaf9747de77d1`
- **Dataset SHA-256**: `1f81cc99413345e88b1d47b8bcc136d92bd388521eac9a61807827ba9acc2e2d`
- **Dataset File Path**: [eval_dataset.json](../../eval_dataset.json)
- **Snapshot Folder**: [`snapshots/`](snapshots/)
  - [`manifest.json`](snapshots/manifest.json) — Commit hash, model details, config source flag
  - [`system_prompt.txt`](snapshots/system_prompt.txt) — Exact Bedrock search intent system prompt
  - [`config.yaml`](snapshots/config.yaml) — Whitelist schemas, thresholds, guardrail rules
  - [`eval_summary.json`](snapshots/eval_summary.json) — Faithfulness rate, injection block rate, token & cost totals

## 2. Rerun Command

To reproduce this evaluation run exact setup, execute:
```bash
python3 tests/eval_natural_language_product_search_mvp/run_eval.py --port 32962 --runtime-env local
```

## 3. Quick Summary of Results

| Metric | Value |
| :--- | :--- |
| **Total Cases** | `10` |
| **Passed Cases** | `8` |
| **Failed Cases** | `2` |
| **Pass Rate** | **80.0%** |
| **Faithfulness Rate (`return_products`)** | `0.750` |
| **Avg Recall (`return_products`)** | `0.833` |
| **Total Input Tokens** | `18,394` |
| **Total Output Tokens** | `994` |
| **Total Estimated Cost (USD)** | `$0.008003` |

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
| `TC-01` | `vietnamese_nlp` | *"có những loại kính thiên văn nào?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `1YMWWN1N4O, 66VCHSJNUP, OLJCESPC7Z` | `False` | 1.00 | 1.00 | `1841` | `113` | `$0.000835` | **✅ PASS** |
| `TC-02` | `vietnamese_nlp` | *"đèn pin"* | `LS4PSXUNUM` | `LS4PSXUNUM` | `False` | 1.00 | 1.00 | `1836` | `99` | `$0.000798` | **✅ PASS** |
| `TC-03` | `vietnamese_nlp` | *"có kính thiên văn nào rẻ rẻ không?"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `1842` | `105` | `$0.000815` | **✅ PASS** |
| `TC-04` | `vietnamese_nlp` | *"màn lọc kính thiên văn"* | `6E92ZMYYFZ` | `0PUK6V6EV0, 6E92ZMYYFZ` | `False` | 0.50 | 1.00 | `1839` | `84` | `$0.000762` | **✅ PASS** |
| `TC-05` | `vietnamese_nlp` | *"chòa bạn"* | `[]` | `[]` | `True` | — | — | `1836` | `53` | `$0.000683` | **✅ PASS** |
| `TC-06` | `vietnamese_nlp` | *"tôi muốn mua kính thiên văn rẻ nhất"* | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `OLJCESPC7Z, 1YMWWN1N4O, 66VCHSJNUP` | `False` | 1.00 | 1.00 | `1842` | `106` | `$0.000818` | **✅ PASS** |
| `TC-07` | `vietnamese_nlp` | *"hi"* | `[]` | `[]` | `True` | — | — | `1834` | `53` | `$0.000683` | **✅ PASS** |
| `TC-08` | `vietnamese_nlp` | *"có truyện tranh không?"* | `HQTGWGPNH4` | `[]` | `True` | — | — | `1839` | `98` | `$0.000797` | **❌ FAIL** |
| `TC-09` | `vietnamese_nlp` | *"tôi muốn mua 1 bộ one piece"* | `[]` | `[]` | `True` | — | — | `1842` | `159` | `$0.000950` | **✅ PASS** |
| `TC-10` | `vietnamese_nlp` | *"thêm cái đắt nhất vào giỏ hàng"* | `66VCHSJNUP` | `[]` | `True` | — | — | `1843` | `124` | `$0.000863` | **❌ FAIL** |
