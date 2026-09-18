"""Run an isolated adaptation experiment on a user-confirmed labeled CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import train_text_detector as trainer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--base-model', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.dataset.exists():
        raise ValueError('Use fresh output and dataset paths to preserve existing artifacts')
    # Conservative boundaries: there is no exact prompt mapping in this corpus.
    topic_splits = {'daily_life': 'train', 'entertainment': 'train',
                    'technology': 'train', 'education': 'validation',
                    'news': 'calibration', 'health': 'test'}
    rows = []
    id_topics = {}
    with args.corpus.open(encoding='utf-8-sig', newline='') as handle:
        for raw in csv.DictReader(handle):
            topic = raw['topic'].strip().casefold()
            original_id = raw['original_id']
            if id_topics.setdefault(original_id, topic) != topic:
                raise ValueError('An original_id crosses topic boundaries')
            rows.append({'text': raw['text'], 'label': raw['label'],
                         'group_id': 'confirmed-topic:' + topic,
                         'split': topic_splits[topic], 'language': raw['language'],
                         'domain': raw['content_type'],
                         'source': raw['ai_model'] if raw['label'] == 'ai' else 'human'})
    args.dataset.parent.mkdir(parents=True, exist_ok=True)
    with args.dataset.open('x', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    samples = trainer.load_samples(args.dataset)
    splits = trainer.split_samples(samples, validation_ratio=.1, calibration_ratio=.1,
                                   test_ratio=.15, seed=42)
    trainer.validate_splits(splits)
    args.output_dir.mkdir(parents=True)
    manifest = {
        'corpus': str(args.corpus.resolve()),
        'corpus_sha256': hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
        'base_model': str(args.base_model.resolve()),
        'authorship_basis': 'User authorized use after provenance clarification.',
        'split_counts': dict(Counter(row['split'] for row in rows)),
        'topic_splits': topic_splits,
        'limitations': [
            'Generator versions are unknown; sources identify model families only.',
            'Prior checkpoint training exposure is unknown; test metrics are internal diagnostics.',
            'Only six topic groups; each held-out split contains a single topic.',
            'No newly generated adversarial examples; prior synthetic corpora are excluded.',
        ],
        'deployment': 'Separate candidate; no production configuration changes.',
    }
    trainer.write_json(args.output_dir / 'run_manifest.json', manifest)
    trainer.seed_everything(42)
    tokenizer = trainer.AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    model = trainer.AutoModelForSequenceClassification.from_pretrained(
        args.base_model, local_files_only=True, trust_remote_code=False)
    odds = trainer.predict_document_log_odds(model, tokenizer, splits['validation'],
        device=trainer.torch.device('cpu'), max_length=512, stride=64, batch_size=8)
    baseline = trainer.evaluate_probabilities(trainer.probabilities_from_log_odds(odds, 1.),
                                              [sample.label for sample in splits['validation']])
    trainer.write_json(args.output_dir / 'baseline_validation.json', baseline)
    print('Baseline validation:', json.dumps(baseline), flush=True)
    del model, tokenizer
    sys.argv = [str(Path(trainer.__file__)), '--dataset', str(args.dataset),
        '--base-model', str(args.base_model), '--output-dir', str(args.output_dir),
        '--epochs', '5', '--patience', '2', '--batch-size', '8', '--learning-rate', '2e-5',
        '--max-length', '512', '--freeze-encoder', '--local-files-only', '--device', 'cpu']
    trainer.main()


if __name__ == '__main__':
    main()
