# Natural-Language Product Search MVP — Evaluation Framework

This directory contains the evaluation framework for **TF4AIO-4** (Natural-language product search MVP).

## Overview

The framework verifies that the `SearchProductsAIAssistant` gRPC RPC correctly:

1. Parses natural-language queries into structured search intents via AWS Bedrock.
2. Filters the product catalog by category, price range, and keywords.
3. Refuses out-of-scope queries and prompt injection attempts.
4. Returns only products that exist in the real catalog (grounding shield).
5. Provides an evidence trace for every response.

## Directory Structure

| File | Responsibility |
|------|---------------|
| `db_source.py` | Parses `init.sql` to extract real product data from `catalog.products` |
| `dataset_builder.py` | Builds test cases deterministically from product data (ground truths computed, never hardcoded) |
| `generate_dataset.py` | CLI: loads products → builds test cases → writes `eval_dataset.json` with SHA256 hash |
| `grounding.py` | Validates that returned product IDs are a subset of the real catalog |
| `evaluator.py` | Single `evaluate()` function for ALL test cases, fail-closed on unknown results |
| `run_eval.py` | CLI: reads dataset, calls `SearchProductsAIAssistant` via gRPC, runs evaluator, writes evidence JSON + report |
| `eval_dataset.json` | Generated test dataset (DO NOT edit manually — regenerate via `generate_dataset.py`) |
| `evidence/` | Directory containing evidence JSON files from actual eval runs |

## Intent Groups (D1 Compliance)

The dataset contains ≥15 test cases across ≥4 intent groups:

| Group | Description | Expected Behavior |
|-------|-------------|-------------------|
| `exact_match` | Query uses exact product name | Returns matching product(s) |
| `category` | Query filters by category (e.g., "telescopes") | Returns all products in that category |
| `price_range` | Query filters by price (e.g., "under $100") | Returns products within price range |
| `attribute_filter` | Combined category + price filter | Returns products matching both filters |
| `safety` | Out-of-domain queries, empty queries | Refused (`refused=true`, empty results) |
| `injection` | Prompt injection attempts | Refused (`refused=true`, empty results) |

## Quick Start

### Prerequisites

- The `product-reviews` service must be running (via `docker compose up` in `techx-corp-platform/`)
- Python 3.10+ with the `product-reviews` virtual environment

### Generate Dataset

From the `techx-corp-platform/` directory:

```bash
make generate-nl-dataset
```

Or manually:

```bash
python3 tests/eval_natural_language_product_search_mvp/generate_dataset.py \
  --source sql \
  --sql-file techx-corp-platform/src/postgresql/init.sql
```

### Run Evaluation

From the `techx-corp-platform/` directory:

```bash
make run-nl-eval
```

Or manually (replace `PORT` with the actual gRPC port of `product-reviews`):

```bash
./src/product-reviews/venv/bin/python \
  ../tests/eval_natural_language_product_search_mvp/run_eval.py \
  --port PORT \
  --runtime-env local
```

### Read Results

- **Evidence JSON**: `evidence/results_<git_sha>_<timestamp>.json`
- **Report**: `report.md` (auto-generated from evidence files)

## Current Status

> [!IMPORTANT]
> The `SearchProductsAIAssistant` RPC has been added to `demo.proto` and implemented
> in `product_reviews_server.py`. Running the evaluation requires:
> 1. A running `product-reviews` service with the updated code (via Docker Compose)
> 2. AWS Bedrock credentials configured (for LLM intent parsing)
>
> If the RPC is not available, `run_eval.py` will raise a clear error — it will
> **never** mock the RPC or fabricate results.

## Evidence Rules

Every evidence file contains:

| Field | Description |
|-------|-------------|
| `git_sha` | Git commit hash at time of run |
| `timestamp_utc` | UTC timestamp of run |
| `runtime_env` | `local` / `staging` / `production` (explicitly declared) |
| `model_id` | Bedrock model ID used |
| `dataset_sha256` | SHA256 of the dataset used (verified before eval) |
| `results` | Per-test-case pass/fail with evaluator output |

**Anti-fabrication guarantees:**

- Number of evidence files on disk = number of runs claimed in report
- Dataset hash in evidence must match hash recomputed from `eval_dataset.json`
- All results come from real gRPC calls — no mocks, no hardcoded passes
- Unknown/ambiguous results fail closed (`passed=false`)

## Schema Assumptions (Verified)

These were verified against the actual repository before building this framework:

- `catalog.products` columns: `id`, `name`, `description`, `picture`, `price_currency_code`, `price_units`, `price_nanos`, `categories`
- `categories` is a comma-separated text field (e.g., `'accessories,telescopes'`)
- Price = `price_units + price_nanos / 1_000_000_000` (e.g., units=101, nanos=960000000 → $101.96)
- `ProductCatalogService.ListProducts(Empty)` returns all 10 products
- `ProductReviewService.SearchProductsAIAssistant` is the new RPC for NL search

## Reproduction

From a clean git clone:

```bash
# 1. Start services
cd techx-corp-platform
docker compose up -d

# 2. Generate dataset
make generate-nl-dataset

# 3. Run evaluation
make run-nl-eval
```

Results will differ across runs due to LLM non-determinism (temperature=0 reduces but
does not eliminate variance). The dataset hash and product catalog are deterministic.
