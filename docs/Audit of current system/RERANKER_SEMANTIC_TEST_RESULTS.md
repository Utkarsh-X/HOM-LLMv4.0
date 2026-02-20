# RERANKER SEMANTIC TEST RESULTS

- Model ID: `tomaarsen/Qwen3-Reranker-0.6B-seq-cls`

## Controlled Pairs
```json
[
  {
    "query": "How does logging work?",
    "doc": "The logging module defines LogManager and handlers.",
    "label": "high"
  },
  {
    "query": "How does logging work?",
    "doc": "This file defines image resizing utilities.",
    "label": "moderate"
  },
  {
    "query": "How does logging work?",
    "doc": "Random unrelated configuration constants.",
    "label": "irrelevant"
  }
]
```

## Raw Logits
```json
[
  0.85660320520401,
  1.0309481620788574,
  0.9240884184837341
]
```

## Ranking (High -> Low)
```json
[
  {
    "label": "moderate",
    "query": "How does logging work?",
    "doc": "This file defines image resizing utilities.",
    "logit": 1.0309481620788574
  },
  {
    "label": "irrelevant",
    "query": "How does logging work?",
    "doc": "Random unrelated configuration constants.",
    "logit": 0.9240884184837341
  },
  {
    "label": "high",
    "query": "How does logging work?",
    "doc": "The logging module defines LogManager and handlers.",
    "logit": 0.85660320520401
  }
]
```

- monotonic_expected_high_gt_moderate_gt_irrelevant: `False`

## Forensic Conclusion
- In this controlled natural-language toy set, logits were not monotonic with expected relevance labels.
- This does not indicate random head initialization (load integrity checks are clean), but it does indicate semantic misalignment on this probe.

## Full Artifacts
- JSON: `eval\runs\reranker_warning_forensic\20260218_190124\semantic_test_results.json`
