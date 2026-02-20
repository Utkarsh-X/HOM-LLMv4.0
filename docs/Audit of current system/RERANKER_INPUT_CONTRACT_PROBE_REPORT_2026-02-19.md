# RERANKER INPUT CONTRACT PROBE (PHASE 1)

- Generated (UTC): `2026-02-19T15:37:00.241088+00:00`
- Probe queries: `[5, 11, 13, 6, 2, 18]`

## Summary

- Mean tau (legacy [SEP]): `-0.0502`
- Mean tau (official contract): `0.5421`
- Mean tau improvement (official - legacy): `0.5923`
- Mean P@1 legacy -> official: `0.1667` -> `0.8333`
- Mean P@3 legacy -> official: `0.2778` -> `0.6111`
- Mean truncation rate legacy -> official: `0.0722` -> `0.0000`
- Mean rerank input token length (official): `235.95`
- Mean raw logit mean/std (official): `-4.9213` / `4.3800`
- Mean sigmoid mean/std (official): `0.1828` / `0.2558`
- Acceptance (>= +0.10 tau improvement): `True`

## Per-Query

| Query | Tau Legacy | Tau Official | Delta | P@1 Legacy | P@1 Official | P@3 Legacy | P@3 Official | Trunc Legacy | Trunc Official | TokLen Official | raw mean/std | sigmoid mean/std |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | -0.3586 | 0.8367 | 1.1952 | 0.0000 | 1.0000 | 0.6667 | 0.6667 | 0.2000 | 0.0000 | 400.80 | -0.7003/6.7710 | 0.4345/0.4647 |
| 11 | -0.4046 | 0.3709 | 0.7754 | 0.0000 | 0.0000 | 0.0000 | 0.6667 | 0.0000 | 0.0000 | 195.22 | -6.6710/1.7135 | 0.0078/0.0205 |
| 13 | 0.5774 | 0.5774 | 0.0000 | 1.0000 | 1.0000 | 0.6667 | 0.6667 | 0.1667 | 0.0000 | 300.83 | -6.5968/5.9373 | 0.1666/0.3719 |
| 6 | 0.1498 | 0.3162 | 0.1664 | 0.0000 | 1.0000 | 0.0000 | 0.3333 | 0.0000 | 0.0000 | 121.75 | -7.7566/1.8575 | 0.0021/0.0047 |
| 2 | 0.0219 | 0.5468 | 0.5250 | 0.0000 | 1.0000 | 0.0000 | 0.6667 | 0.0000 | 0.0000 | 142.20 | -6.5249/3.7790 | 0.0817/0.2283 |
| 18 | -0.2874 | 0.6044 | 0.8918 | 0.0000 | 1.0000 | 0.3333 | 0.6667 | 0.0667 | 0.0000 | 254.87 | -1.2780/6.2217 | 0.4045/0.4448 |
