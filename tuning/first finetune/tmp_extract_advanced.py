import os
import re
import glob

folder = r"D:\HOM-LLM(v2.0)\eval\folder30_run_scores"
files = glob.glob(os.path.join(folder, "Batch-*.md"))
files.sort(key=lambda x: int(re.search(r'Batch-(\d+)', x).group(1)))

data = []

metric_names = [
    "Semantic Correctness", "Factual Consistency", "Completeness",
    "Clarity", "Relevance", "Hallucination Safety", "Verbosity (lower=better)", "Overall Quality"
]

def parse_part(part, provider_name):
    res = {
        'provider': provider_name,
        'improved': 0, 'regressed': 0, 'equal': 0, 'win_rate': 0.0,
        'metrics': {}
    }
    
    m_imp = re.search(r'\[\+\] Improved\s*:\s*(\d+)', part)
    if m_imp: res['improved'] = int(m_imp.group(1))
    
    m_reg = re.search(r'\[-\] Regressed\s*:\s*(\d+)', part)
    if m_reg: res['regressed'] = int(m_reg.group(1))
    
    m_eq = re.search(r'\[=\] Equal\s*:\s*(\d+)', part)
    if m_eq: res['equal'] = int(m_eq.group(1))
    
    m_wr = re.search(r'Win Rate.*:\s*([0-9.]+)%', part)
    if m_wr: res['win_rate'] = float(m_wr.group(1))
    
    # -------------------- OVERALL AVERAGE SCORES (0-10) --------------------
    # parse the last block of scores
    score_blocks = part.split('OVERALL AVERAGE SCORES (0-10)')
    if len(score_blocks) > 1:
        last_block = score_blocks[-1]
        for m_name in metric_names:
            escaped_name = m_name.replace('(', r'\(').replace(')', r'\)')
            # Match ex: "Semantic Correctness     |            9.9 |             9.6"
            idx_match = re.search(escaped_name + r'\s+\|\s+([0-9.]+)\s+\|\s+([0-9.]+)', last_block)
            if idx_match:
                cand = float(idx_match.group(1))
                base = float(idx_match.group(2))
                res['metrics'][m_name] = {'cand': cand, 'base': base, 'delta': round(cand - base, 2)}
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
        run_name = os.path.basename(file).replace('.md', '')
        
        run_data = {'run': run_name, 'gemini': None, 'cerebras': None}

        for part in parts[1:]:
            provider = part.splitlines()[0].strip().lower()
            if "gemini" in provider:
                run_data['gemini'] = parse_part(part, 'gemini')
            elif "cerebras" in provider:
                run_data['cerebras'] = parse_part(part, 'cerebras')
                
        data.append(run_data)
    except Exception as e:
        print(f"Error processing {file}: {e}")

def format_delta(v, reverse_good=False):
    if v is None: return "N/A"
    if v == 0: return "0.00"
    if v > 0: return f"+{v:.2f}"
    return f"{v:.2f}"

output_md = []

for prov in ['gemini', 'cerebras']:
    output_md.append(f"### {prov.capitalize()} - Advanced Analysis")
    output_md.append("*(Note: Verbosity 'lower=better', so a negative delta is an improvement. All other metrics 'higher=better'. Deltas are Candidate - Baseline.)*")
    output_md.append("")
    
    headers = ["Run", "Win Rate", "Imp/Reg/Eq", "Sem. Corr. (\u0394)", "Fact. Cons. (\u0394)", "Completeness (\u0394)", "Clarity (\u0394)", "Relevance (\u0394)", "Halluc. Safe (\u0394)", "Verbosity (\u0394)", "Overall Qual. (\u0394)"]
    output_md.append("| " + " | ".join(headers) + " |")
    output_md.append("|" + "|".join(["---" for _ in headers]) + "|")
    
    for d in data:
        p_data = d[prov]
        if not p_data:
            continue
            
        r_str = f"{p_data['improved']}/{p_data['regressed']}/{p_data['equal']}"
        wr_str = f"{p_data['win_rate']:.1f}%"
        
        m = p_data['metrics']
        def get_dm(name):
            d_val = m.get(name, {}).get('delta')
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
        output_md.append("| " + " | ".join(row) + " |")
    
    output_md.append("")

with open(r"D:\HOM-LLM(v2.0)\eval_advanced.md", "w", encoding="utf-8") as f:
    f.write("\n".join(output_md))
print("Done writing to eval_advanced.md")
