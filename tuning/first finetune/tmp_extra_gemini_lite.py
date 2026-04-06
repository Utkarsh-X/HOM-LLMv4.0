import os
import re

files_to_parse = [r"D:\HOM-LLM(v2.0)\1-15re.md", r"D:\HOM-LLM(v2.0)\16-30re.md"]

run_data = {}

metric_names = [
    "Semantic Correctness", "Factual Consistency", "Completeness",
    "Clarity", "Relevance", "Hallucination Safety", "Verbosity (lower=better)", "Overall Quality"
]

def format_delta(v, reverse_good=False):
    if v is None: return "N/A"
    if v == 0: return "0.00"
    if v > 0: return f"+{v:.2f}"
    return f"{v:.2f}"

def format_val(val, is_delta=False):
    if val is None: return "N/A"
    if is_delta:
        return f"+{val:.2f}" if val > 0 else f"{val:.2f}"
    return f"{val:.2f}"

for file in files_to_parse:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by "Run ID" to isolate each run
    parts = content.split("Run ID          : ")
    for part in parts[1:]:
        run_name = part.splitlines()[0].strip()
        # Find batch file name
        m_batch = re.search(r'ccg30_(\d+)_', run_name)
        if not m_batch:
            continue
        batch_num = int(m_batch.group(1))
        batch_run_name = f"Batch-{batch_num:02d}({run_name})"

        res = {
            'run': batch_run_name,
            'improved': 0, 'regressed': 0, 'equal': 0, 'win_rate': 0.0,
            'metrics': {},
            'gemini_score': None,
            'gemini_base': None,
            'gemini_delta': None
        }
        
        m_imp = re.search(r'\[\+\] Improved\s*:\s*(\d+)', part)
        if m_imp: res['improved'] = int(m_imp.group(1))
        
        m_reg = re.search(r'\[-\] Regressed\s*:\s*(\d+)', part)
        if m_reg: res['regressed'] = int(m_reg.group(1))
        
        m_eq = re.search(r'\[=\] Equal\s*:\s*(\d+)', part)
        if m_eq: res['equal'] = int(m_eq.group(1))
        
        m_wr = re.search(r'Win Rate.*:\s*([0-9.]+)%', part)
        if m_wr: res['win_rate'] = float(m_wr.group(1))
        
        score_blocks = part.split('OVERALL AVERAGE SCORES (0-10)')
        if len(score_blocks) > 1:
            last_block = score_blocks[-1]
            for m_name in metric_names:
                escaped_name = m_name.replace('(', r'\(').replace(')', r'\)')
                idx_match = re.search(escaped_name + r'\s+\|\s+([0-9.]+)\s+\|\s+([0-9.]+)', last_block)
                if idx_match:
                    cand = float(idx_match.group(1))
                    base = float(idx_match.group(2))
                    res['metrics'][m_name] = {'cand': cand, 'base': base, 'delta': round(cand - base, 2)}
                    if m_name == "Overall Quality":
                        res['gemini_score'] = cand
                        res['gemini_base'] = base
                        res['gemini_delta'] = round(cand - base, 2)
                else:
                    res['metrics'][m_name] = {'cand': None, 'base': None, 'delta': None}
        
        # metric for ranking = Score + Delta
        if res['gemini_score'] is not None and res['gemini_delta'] is not None:
            res['metric_score'] = round(res['gemini_score'] + res['gemini_delta'], 2)
        else:
            res['metric_score'] = None

        run_data[batch_run_name] = res

# 1. Update eval_advanced.md
with open(r"D:\HOM-LLM(v2.0)\eval_advanced.md", "r", encoding="utf-8") as f:
    adv_content = f.read()

adv_lines = ["", "### Gemini 3.1 flash lite - Advanced Analysis", "*(Note: Verbosity 'lower=better', so a negative delta is an improvement. All other metrics 'higher=better'. Deltas are Candidate - Baseline.)*", ""]
headers = ["Run", "Win Rate", "Imp/Reg/Eq", "Sem. Corr. (\u0394)", "Fact. Cons. (\u0394)", "Completeness (\u0394)", "Clarity (\u0394)", "Relevance (\u0394)", "Halluc. Safe (\u0394)", "Verbosity (\u0394)", "Overall Qual. (\u0394)"]
adv_lines.append("| " + " | ".join(headers) + " |")
adv_lines.append("|" + "|".join(["---" for _ in headers]) + "|")

for run_key in sorted(run_data.keys(), key=lambda x: int(re.search(r'Batch-(\d+)', x).group(1))):
    p_data = run_data[run_key]
    r_str = f"{p_data['improved']}/{p_data['regressed']}/{p_data['equal']}"
    wr_str = f"{p_data['win_rate']:.1f}%"
    
    def get_dm(name):
        d_val = p_data['metrics'].get(name, {}).get('delta')
        return format_delta(d_val)
        
    row = [
        run_key.replace('Batch-', 'B-'),
        wr_str,
        r_str,
        get_dm("Semantic Correctness"),
        get_dm("Factual Consistency"),
        get_dm("Completeness"),
        get_dm("Clarity"),
        get_dm("Relevance"),
        get_dm("Hallucination Safety"),
        get_dm("Verbosity (lower=better)"),
        get_dm("Overall Quality")
    ]
    adv_lines.append("| " + " | ".join(row) + " |")

with open(r"D:\HOM-LLM(v2.0)\eval_advanced.md", "a", encoding="utf-8") as f:
    f.write("\n" + "\n".join(adv_lines))


# 2. Update eval_rankings.md
with open(r"D:\HOM-LLM(v2.0)\eval_rankings.md", "r", encoding="utf-8") as f:
    rank_content = f.read()

rank_lines = ["", "### Gemini 3.1 flash lite Rankings", "Rank calculated using the equation: `Score + Delta`", ""]
rank_lines.append("| Rank | Run | Score | Delta | Metric (Score + Delta) |")
rank_lines.append("|:---:|---|:---:|:---:|:---:|")

sorted_runs = sorted(list(run_data.values()), key=lambda x: x['metric_score'] if x['metric_score'] is not None else -1000, reverse=True)
for i, d in enumerate(sorted_runs):
    rank_lines.append(f"| {i+1} | {d['run']} | {format_val(d['gemini_score'])} | {format_val(d['gemini_delta'], True)} | {format_val(d['metric_score'])} |")

with open(r"D:\HOM-LLM(v2.0)\eval_rankings.md", "a", encoding="utf-8") as f:
    f.write("\n" + "\n".join(rank_lines))


# 3. Update eval_scores_table_vertical.md
with open(r"D:\HOM-LLM(v2.0)\eval_scores_table_vertical.md", "r", encoding="utf-8") as f:
    vert_content = f.read().splitlines()

for idx, line in enumerate(vert_content):
    if line.startswith("| Run |"):
        vert_content[idx] = line[:-2] + " | Gemini 3.1 flash lite Score | Gemini 3.1 flash lite Delta |"
    elif line.startswith("|---|"):
        vert_content[idx] = line + "---|---|"
    elif line.startswith("| Batch-"):
        m = re.search(r'Batch-\d+\([^)]+\)', line)
        if m:
            run_key = m.group(0)
            if run_key in run_data:
                d = run_data[run_key]
                vert_content[idx] = line[:-2] + f" | {format_val(d['gemini_score'])} | {format_val(d['gemini_delta'], True)} |"
            else:
                vert_content[idx] = line[:-2] + " | N/A | N/A |"

with open(r"D:\HOM-LLM(v2.0)\eval_scores_table_vertical.md", "w", encoding="utf-8") as f:
    f.write("\n".join(vert_content))

print("Extraction and appending done successfully.")
