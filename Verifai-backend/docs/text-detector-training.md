# Text detector training and accuracy protocol

AI-writing detection is a distribution-classification problem, not proof of authorship. Accuracy
must be measured on the languages, genres, generators, editing patterns, and text lengths that
VeriFai will actually receive. Do not train on a few hand-written examples or report the training
score as product accuracy.

## Dataset contract

Use UTF-8 CSV or JSONL with these fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `text` | yes | Final text shown to the detector, 20–10,000 characters |
| `label` | yes | `human`/`0` or `ai`/`1` |
| `group_id` | yes | Shared prompt, source document, author, or derivation chain |
| `split` | no | `train`, `validation`, `calibration`, or `test`; set it on every row or none |
| `language` | no | Language or locale used for subgroup evaluation |
| `domain` | no | Essay, news, social, academic, code explanation, and so on |
| `source` | no | Human corpus or generator/model family |

Example JSONL rows:

```json
{"text":"...", "label":"human", "group_id":"prompt-0001", "split":"train", "language":"en", "domain":"essay", "source":"human-collected"}
{"text":"...", "label":"ai", "group_id":"prompt-0001", "split":"train", "language":"en", "domain":"essay", "source":"generator-family-a"}
```

`group_id` is the leakage boundary. Human answers, AI answers, paraphrases, continuations, and
edited variants originating from the same prompt or document must share it. If explicit splits
are supplied, the trainer rejects a group found in more than one split. Exact duplicate text is
deduplicated, and conflicting labels fail the run.

Build the calibration and test splits before model development and keep the test split frozen.
The validation split selects the training epoch, calibration fits probabilities and abstention
thresholds, and test is opened only for the final audit. Test should include unseen human authors
and unseen generator versions. Include difficult negatives: polished professional prose,
templates, second-language writing, accessibility tools, grammar correction, short answers, and
formulaic institutional text. Include difficult positives: temperature variation, deliberate
errors, paraphrasing, partial human edits, translations, and mixed human/AI passages. Record user
consent and dataset licensing; do not collect private text without authorization.

For a credible product evaluation, use hundreds of documents per class in validation and test,
with enough examples in each important language/domain subgroup to publish a separate result.
The trainer only enforces a tiny mechanical minimum so smoke-test datasets remain possible.

### Combining an AI-only corpus

An AI corpus with generator provenance but no `label` field can contribute verified AI examples,
but it cannot train or measure a human-versus-AI detector by itself. Pair it with a separately
labeled human/AI corpus, deduplicate it, and keep all variants from the same prompt in one split.
Do not randomly split generated variants from the same prompt: that leaks prompt wording into the
test set and inflates the result.

`scripts/build_text_detector_dataset.py` creates an explicit, group-safe JSONL dataset from the
local current AI corpus and an already labeled corpus:

```powershell
python scripts/build_text_detector_dataset.py `
  --ai-corpus C:\Users\dever\Downloads\datasets_10k.jsonl `
  --labeled-corpus C:\Users\dever\Downloads\test_predictions_with_breakdown.csv `
  --output C:\Users\dever\Downloads\verifai_ai_human_current_v1.jsonl
```

The generated dataset is a candidate-training artifact, not proof that the historical labeled
rows are representative of future human writing. Keep the source data and generated output out of
version control unless their licenses and consent permit committing them.

## Training

Run from `Verifai-backend` with a new output directory:

```powershell
python scripts/train_text_detector.py `
  --dataset data/ai-writing-v1.jsonl `
  --base-model C:\Users\dever\Downloads\xlmr-ai-human-best `
  --output-dir C:\Users\dever\Downloads\xlmr-ai-human-v2 `
  --epochs 3 `
  --batch-size 4 `
  --gradient-accumulation 4 `
  --target-precision 0.90 `
  --local-files-only
```

For a fast, low-risk distribution-adaptation candidate on a CPU-only machine, start by freezing
the encoder and training only the classifier head. Always save it to a new output directory and
promote it only if its untouched test report clears the release gate:

```powershell
python scripts/train_text_detector.py `
  --dataset C:\Users\dever\Downloads\verifai_ai_human_current_v1.jsonl `
  --base-model C:\Users\dever\Downloads\xlmr-ai-human-best `
  --output-dir C:\Users\dever\Downloads\xlmr-ai-human-current-candidate `
  --epochs 1 `
  --learning-rate 0.0001 `
  --batch-size 16 `
  --freeze-encoder `
  --local-files-only
```

`--human-loss-weight` raises the relative penalty for labeling verified human text as AI while
keeping the average loss scale stable. Its default is `1.0`; values above that are experimental and
must improve a fresh group-safe test split before release. Tune from validation data only, then
evaluate the chosen setting once on a fresh group-safe test split.

The pipeline:

1. splits whole groups, never individual variants;
2. class-balances document contribution and prevents long documents from dominating loss;
3. trains overlapping windows sampled across each long document;
4. selects the best epoch on validation balanced accuracy with early stopping;
5. learns a temperature and human/AI abstention thresholds from a separate calibration split;
6. evaluates the frozen model and policy once on test;
7. writes `evaluation_report.json` and `text_calibration.json` beside the model.

Production inference automatically loads `text_calibration.json`. Without it, the API explicitly
labels scores as uncalibrated. An invalid artifact fails closed instead of silently returning
misleading percentages.

## Release gate

Before changing `TEXT_MODEL_PATH`, review the held-out report. At minimum, compare balanced
accuracy, class precision/recall, ROC AUC, Brier score, expected calibration error, review rate,
accuracy on confident predictions, and every important language/domain/source subgroup. Choose
release thresholds before looking at test results. Keep the previous model available for rollback.

Re-evaluate after adding a language, input genre, generator family, prompt style, or major model
version. Monitor aggregate score and review-rate drift without storing raw user text. Never use a
detector result as the sole basis for punishment, grading, hiring, moderation, or an accusation.
