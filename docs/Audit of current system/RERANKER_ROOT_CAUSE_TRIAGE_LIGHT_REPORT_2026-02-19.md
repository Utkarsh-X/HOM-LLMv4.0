# RERANKER ROOT-CAUSE TRIAGE REPORT (LIGHTWEIGHT)

- Generated (UTC): `2026-02-19T06:32:32.686693+00:00`
- Probe queries: `[5, 11, 13, 6, 2, 18]`
- Hurt: `[5, 11]`
- Helped slightly: `[13, 6]`
- Neutral/mixed: `[2, 18]`

## Compact Summary Table (Phase 1 A/B/C)

| Variant | Mean Kendall tau vs judged | Mean P@1 | Mean P@3 |
|---|---:|---:|---:|
| A Original | -0.1498 | 0.1667 | 0.1111 |
| B Focused | -0.0174 | 0.0000 | 0.2778 |
| C Minimal slice | -0.2022 | 0.0000 | 0.1111 |

- Mean tau delta (B-A): `0.1325`
- Mean tau delta (C-A): `-0.0523`
- Mean tau delta (best reduced - A): `0.1330`

## Per-Query Deltas

| Query | Group | Label source | Tau A | Tau B | Tau C | B-A | C-A | P@1 A | P@1 B | P@1 C |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | hurt | existing_cache | -0.3536 | -0.2905 | -0.4125 | 0.0631 | -0.0589 | 0.0000 | 0.0000 | 0.0000 |
| 11 | hurt | existing_cache | -0.3760 | -0.3917 | -0.3886 | -0.0156 | -0.0125 | 0.0000 | 0.0000 | 0.0000 |
| 13 | helped_slightly | existing_cache | -0.0704 | 0.3621 | -0.3051 | 0.4325 | -0.2347 | 1.0000 | 0.0000 | 0.0000 |
| 6 | helped_slightly | existing_cache | 0.2164 | 0.1897 | 0.1498 | -0.0267 | -0.0666 | 0.0000 | 0.0000 | 0.0000 |
| 2 | neutral_mixed | existing_cache | -0.0443 | 0.0443 | 0.0266 | 0.0886 | 0.0709 | 0.0000 | 0.0000 | 0.0000 |
| 18 | neutral_mixed | existing_cache | -0.2711 | -0.0182 | -0.2832 | 0.2529 | -0.0120 | 0.0000 | 0.0000 | 0.0000 |

## Formatting Sensitivity (Phase 2)

| Format | Mean Kendall tau | Mean P@1 | Mean P@3 |
|---|---:|---:|---:|
| Format 1 current | -0.1498 | 0.1667 | 0.1111 |
| Format 2 Query/Code | -0.0311 | 0.1667 | 0.2222 |
| Format 3 XML-like | 0.3899 | 0.1667 | 0.4444 |

- Mean tau delta (best format - current): `0.5397`
- Mean cross-format Spearman f1/f2: `0.8022`
- Mean cross-format Spearman f1/f3: `-0.0273`

## Length & Lexical Bias (Phase 3)

- Mean corr(length, judged): `0.5008`
- Mean corr(lexical overlap, judged): `0.6756`
- Mean corr(rerank, judged): `-0.1535`
- Mean corr(lexical - rerank): `0.8291`
- Mean corr(length - rerank): `0.6543`

## Root-Cause Classification

- ROOT_CAUSE = `input_contract`
- CONFIDENCE_LEVEL = `high`
- Mean tau improvement used for gate = `0.5397`
- Full-sweep gate passed = `True`
- Recommendation = `continue`
