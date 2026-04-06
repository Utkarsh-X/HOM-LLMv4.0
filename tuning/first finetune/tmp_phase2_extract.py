import os
import re
import glob

input_dir = r"D:\HOM-LLM(v2.0)\eval\folder15_run_score(Phase2)"
files = glob.glob(os.path.join(input_dir, "Batch-*.md"))
files.sort(key=lambda x: int(re.search(r'Batch-(\d+)', x).group(1)))

data = []

metric_names = [
    "Semantic Correctness", "Factual Consistency", "Completeness",
    "Clarity", "Relevance", "Hallucination Safety", "Verbosity (lower=better)", "Overall Quality"
]

def format_val(val, is_delta=False):
    if val is None: return "N/A"
    if is_delta:
        return f"+{val:.2f}" if val > 0 else f"{val:.2f}"
    return f"{val:.2f}"

def format_delta(v):
    if v is None: return "N/A"
    if v == 0: return "0.00"
    if v > 0: return f"+{v:.2f}"
    return f"{v:.2f}"

def parse_part(part, provider_name):
    res = {
        'provider': provider_name,
        'improved': 0, 'regressed': 0, 'equal': 0, 'win_rate': 0.0,
        'metrics': {},
        'score': None,
        'base': None,
        'delta': None,
        'metric_score': None
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
                delta = round(cand - base, 2)
                res['metrics'][m_name] = {'cand': cand, 'base': base, 'delta': delta}
                if m_name == "Overall Quality":
                    res['score'] = cand
                    res['base'] = base
                    res['delta'] = delta
                    res['metric_score'] = round(cand + delta, 2)
            else:
                res['metrics'][m_name] = {'cand': None, 'base': None, 'delta': None}
    else:
        for m_name in metric_names:
            res['metrics'][m_name] = {'cand': None, 'base': None, 'delta': None}
            
    return res

for file in files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        parts = content.split("Judge provider: ")
        run_name_full = os.path.basename(file).replace('.md', '')
        
        run_data = {'run': run_name_full, 'gemini': None, 'cerebras': None}

        for part in parts[1:]:
            provider = part.splitlines()[0].strip().lower()
            if "gemini" in provider:
                run_data['gemini'] = parse_part(part, 'gemini')
            elif "cerebras" in provider:
                run_data['cerebras'] = parse_part(part, 'cerebras')
                
        data.append(run_data)
    except Exception as e:
        print(f"Error processing {file}: {e}")

# 1. EVAL RANKINGS
rank_lines = []

rank_lines.extend(["### Gemini 3.1 flash lite Rankings", "Rank calculated using the equation: `Score + Delta`", ""])
rank_lines.append("| Rank | Run | Score | Delta | Metric (Score + Delta) |")
rank_lines.append("|:---:|---|:---:|:---:|:---:|")

gemini_sorted = sorted([d for d in data if d['gemini'] and d['gemini']['metric_score'] is not None], key=lambda x: x['gemini']['metric_score'], reverse=True)
for i, d in enumerate(gemini_sorted):
    p = d['gemini']
    rank_lines.append(f"| {i+1} | {d['run']} | {format_val(p['score'])} | {format_val(p['delta'], True)} | {format_val(p['metric_score'])} |")

rank_lines.extend(["", "### Cerebras Qwen-3 235B Rankings", "Rank calculated using the equation: `Score + Delta`", ""])
rank_lines.append("| Rank | Run | Score | Delta | Metric (Score + Delta) |")
rank_lines.append("|:---:|---|:---:|:---:|:---:|")

cerebras_sorted = sorted([d for d in data if d['cerebras'] and d['cerebras']['metric_score'] is not None], key=lambda x: x['cerebras']['metric_score'], reverse=True)
for i, d in enumerate(cerebras_sorted):
    p = d['cerebras']
    rank_lines.append(f"| {i+1} | {d['run']} | {format_val(p['score'])} | {format_val(p['delta'], True)} | {format_val(p['metric_score'])} |")

with open(os.path.join(input_dir, "phase2_eval_rankings.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(rank_lines))

# 2. EVAL ADVANCED
adv_lines = []

for prov_key, title in [('gemini', 'Gemini 3.1 flash lite'), ('cerebras', 'Cerebras Qwen-3 235B')]:
    adv_lines.extend([f"### {title} - Advanced Analysis", "*(Note: Verbosity 'lower=better', so a negative delta is an improvement. All other metrics 'higher=better'. Deltas are Candidate - Baseline.)*", ""])
    headers = ["Run", "Win Rate", "Imp/Reg/Eq", "Sem. Corr. (\u0394)", "Fact. Cons. (\u0394)", "Completeness (\u0394)", "Clarity (\u0394)", "Relevance (\u0394)", "Halluc. Safe (\u0394)", "Verbosity (\u0394)", "Overall Qual. (\u0394)"]
    adv_lines.append("| " + " | ".join(headers) + " |")
    adv_lines.append("|" + "|".join(["---" for _ in headers]) + "|")
    
    for d in data:
        p = d.get(prov_key)
        if not p: continue
        
        r_str = f"{p['improved']}/{p['regressed']}/{p['equal']}"
        wr_str = f"{p['win_rate']:.1f}%"
        
        def get_dm(name):
            d_val = p['metrics'].get(name, {}).get('delta')
            return format_delta(d_val)
            
        row = [
            d['run'].replace('Batch-', 'B-'),
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
    adv_lines.append("")

with open(os.path.join(input_dir, "phase2_eval_advanced.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(adv_lines))

# 3. VERTICAL SCORES TABLE
vert_lines = []
headers = ["Run", "Gemini 3.1 flash lite Score", "Gemini 3.1 flash lite Delta", "Cerebras Qwen-3 235B Score", "Cerebras Qwen-3 235B Delta"]
vert_lines.append("| " + " | ".join(headers) + " |")
vert_lines.append("|" + "|".join(["---" for _ in headers]) + "|")

for d in data:
    g = d.get('gemini') or {}
    c = d.get('cerebras') or {}
    
    g_score = g.get('score')
    g_delta = g.get('delta')
    c_score = c.get('score')
    c_delta = c.get('delta')
    
    row = [
        d['run'],
        format_val(g_score), format_val(g_delta, True),
        format_val(c_score), format_val(c_delta, True)
    ]
    vert_lines.append("| " + " | ".join(row) + " |")

with open(os.path.join(input_dir, "phase2_eval_scores_table_vertical.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(vert_lines))

print("Successfully wrote phase 2 evaluation reports.")
