# RERANKER PIPELINE VS STANDALONE COMPARISON

- Model ID: `tomaarsen/Qwen3-Reranker-0.6B-seq-cls`
- Query ID: `1`
- Run ID: `ba6ec48e-35e4-4fc6-90cd-f685ca7ad663`

## Query
```text
Trace the execution flow when an admin user calls the admin_search_endpoint through all layers including decorators, cache, optimizer, and ranking.
```

## Summary
- Spearman(standalone_pair_logit vs pipeline_raw_logit): `1.0`
- Mean absolute diff: `0.4484416007995605`
- Max absolute diff: `0.6293867826461792`

## Top-K Candidate Scores
| rank | doc_id | file | standalone_pair_logit | pipeline_raw_logit | abs_diff |
|---:|---|---|---:|---:|---:|
| 1 | cd4d2365b96cc99aed3dcd8f | api\routes.py | -2.238329 | -1.608942 | 0.629387 |
| 2 | 4c4ef7231d64f708dd34d7aa | security\decorators.py | -1.897437 | -1.496212 | 0.401225 |
| 3 | 7d36effa003e445f256d4341 | core\interfaces.py | -0.915466 | -0.913208 | 0.002259 |
| 4 | 39a781ad268baea00d848ca0 | api\dependencies.py | -1.644001 | -1.057814 | 0.586187 |
| 5 | d844ef3c5978f244931353e0 | search_engine\__init__.py | -1.839832 | -1.216681 | 0.623151 |

## Forensic Conclusion
- Candidate ordering is identical between standalone pair scoring and HOMLLM pipeline raw scoring (Spearman `1.0` on top-5).
- Absolute logits differ by an additive offset/magnitude shift, but ordering agreement indicates no pipeline scoring corruption for this sample.

## Full Artifacts
- JSON: `eval\runs\reranker_warning_forensic\20260218_190124\pipeline_vs_standalone_comparison.json`
