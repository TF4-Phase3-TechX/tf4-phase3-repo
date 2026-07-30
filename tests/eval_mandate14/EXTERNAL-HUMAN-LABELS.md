# External human-label calibration

[`external-human-labels-summeval-v1.jsonl`](external-human-labels-summeval-v1.jsonl)
contains 100 labels derived from the
human-annotated SummEval test set:

- 50 summaries with mean expert consistency `<= 2/5` (`human_pass=false`);
- 50 summaries with mean expert consistency `>= 4/5` (`human_pass=true`);
- one selected summary per source document within each class;
- ambiguous scores between 2 and 4 excluded from binary agreement.

SummEval collected five independent crowd annotations and three independent
expert annotations per summary. The committed label uses the published mean of
the three expert consistency scores. It is an external English news
faithfulness calibration set, not AIO1 team labeling and not TF4 production
evidence.

To avoid duplicating copyrighted news articles or generated summaries, the
committed file retains dataset/document IDs, the expert score, binary rule and
SHA-256 of each source/summary. The reproduction script downloads the pinned
dataset revision and fails if any text hash changes.

## Provenance

- Dataset: `mteb/summeval`
- Revision: `bfc121155064afa2d81b5505682ffc0d96f4334c`
- Upstream project: <https://github.com/Yale-LILY/SummEval>
- Processed dataset: <https://huggingface.co/datasets/mteb/summeval>
- License recorded by upstream/processed dataset: MIT
- Citation: Fabbri et al., “SummEval: Re-evaluating Summarization Evaluation”

## Reproduce the committed labels

```powershell
python tests\eval_mandate14\fetch_summeval_human_labels.py --check
```

This proves label-file provenance and byte-for-byte reproducibility. It does
not by itself prove scorer agreement.

## Candidate comparison

Run the pinned `cross-encoder/nli-deberta-v3-small` calibration with:

```powershell
python tests\eval_mandate14\run_external_human_nli.py --batch-size 16
```

The retained failed baseline
[`external-human-nli-report-v1.json`](external-human-nli-report-v1.json)
records:

- 100 human-labeled cases, 50 pass and 50 fail;
- agreement `0.50` and Cohen's κ `0.00`;
- 3/3 explicit contradiction controls rejected;
- zero NLI inputs truncated after per-claim evidence retrieval.

The negative agreement result is intentionally retained. The generic NLI model
is not promoted into the TF4 scorer because it does not agree with the external
expert labels. Passing the contradiction controls alone is insufficient.

The accepted semantic-faithfulness candidate is HHEM-1.0-Open, a DeBERTa
cross-encoder trained for factual consistency after NLI pre-training. The model
card's published `0.5` threshold is used without tuning it on these 100 labels.
The exact `hhem-1.0-open` revision is pinned.

```powershell
python tests\eval_mandate14\run_external_human_factuality.py --batch-size 16
```

[`external-human-factuality-report-v2.json`](external-human-factuality-report-v2.json)
records:

- agreement `0.76` and Cohen's κ `0.52`;
- confusion matrix TP=`36`, TN=`40`, FP=`10`, FN=`14`;
- 3/3 explicit contradiction controls rejected;
- zero model inputs truncated;
- the recorded gate passed: agreement `>=0.70`, κ `>=0.40`, all
  contradiction controls, and zero truncation.

Lexical overlap selects a bounded, source-ordered evidence window only. It does
not decide support. HHEM makes the semantic support decision. This remains an
English news-domain offline calibration; it is not TF4-domain, production, or
hidden-set acceptance evidence.
