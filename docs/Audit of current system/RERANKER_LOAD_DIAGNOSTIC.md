# RERANKER LOAD DIAGNOSTIC

- Timestamp (UTC): 2026-02-18T19:01:32.833983+00:00
- Model ID: `tomaarsen/Qwen3-Reranker-0.6B-seq-cls`
- Model Type: `<class 'transformers.models.qwen3.modeling_qwen3.Qwen3ForSequenceClassification'>`
- Tokenizer Type: `<class 'transformers.models.qwen2.tokenization_qwen2_fast.Qwen2TokenizerFast'>`

## Loading Info
- missing_keys: `0`
- unexpected_keys: `0`
- mismatched_keys: `0`
- error_msgs: `0`
- exact_raw_snippet_warning_count: `0`

## Config
- architectures: `['Qwen3ForSequenceClassification']`
- num_labels: `1`
- model_type: `qwen3`
- commit_hash: `6a5829f5079c66e78d911e06fe21931cc00232f7`

## Classifier Inspection
- classifier_layer_keys: `['score.weight']`
- score.weight exists: `True`
- score.weight shape: `[1, 1024]`
- score.weight norm: `1.1921710968017578`
- score.bias exists: `False`
- score.bias shape: `None`
- score.bias norm: `None`
- classifier.weight exists: `False`
- classifier.bias exists: `False`

## Warnings / stderr
- warnings_count: `0`
```text
(empty)
```

## Missing/Randomly Initialized Keys
```json
[]
```

## Forensic Conclusion
- The checkpoint includes a valid sequence-classification head (`score.weight`) and it is loaded from checkpoint.
- No Hugging Face missing/unexpected key warnings were reproduced in standalone loading.
- The warning seen in pipeline runs is from HOMLLM code (`Non-canonical reranker model`) due model name mismatch against internal canonical constant, not from missing head weights.

## Full Artifacts
- JSON: `eval\runs\reranker_warning_forensic\20260218_190124\load_diagnostic.json`
