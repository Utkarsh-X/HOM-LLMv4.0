import os
import re
import glob

folder = r"D:\HOM-LLM(v2.0)\eval\folder30_run_scores"
files = glob.glob(os.path.join(folder, "Batch-*.md"))

data = []

for file in files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        parts = content.split("Judge provider: ")
        
        run_name = os.path.basename(file).replace('.md', '')
        gemini_score = None
        gemini_baseline = None
        cerebras_score = None
        cerebras_baseline = None

        for part in parts[1:]:
            provider = part.splitlines()[0].strip()
            
            # Find the last "Overall Quality" match in this part
            matches = list(re.finditer(r'Overall Quality\s+\|\s+([0-9.]+)\s+\|\s+([0-9.]+)', part))
            if matches:
                last_match = matches[-1]
                cand = float(last_match.group(1))
                base = float(last_match.group(2))
                
                if "gemini" in provider.lower():
                    gemini_score = cand
                    gemini_baseline = base
                elif "cerebras" in provider.lower():
                    cerebras_score = cand
                    cerebras_baseline = base

        g_delta = round(gemini_score - gemini_baseline, 2) if gemini_score is not None and gemini_baseline is not None else -999
        c_delta = round(cerebras_score - cerebras_baseline, 2) if cerebras_score is not None and cerebras_baseline is not None else -999
        
        # Equation: Rank Metric = Score + Delta
        g_metric = round((gemini_score or 0) + (g_delta if g_delta != -999 else 0), 2)
        c_metric = round((cerebras_score or 0) + (c_delta if c_delta != -999 else 0), 2)

        data.append({
            'run': run_name,
            'gemini_score': gemini_score,
            'gemini_delta': g_delta if g_delta != -999 else None,
            'gemini_metric': g_metric,
            'cerebras_score': cerebras_score,
            'cerebras_delta': c_delta if c_delta != -999 else None,
            'cerebras_metric': c_metric
        })
    except Exception as e:
        print(f"Error processing {file}: {e}")

def format_val(val, is_delta=False):
    if val is None:
        return "N/A"
    if is_delta:
        return f"+{val:.2f}" if val > 0 else f"{val:.2f}"
    return f"{val:.2f}"

output_md = []

# --- GEMINI SECTION ---
output_md.append("### Gemini Rankings")
output_md.append("Rank calculated using the equation: `Score + Delta`")
output_md.append("")
output_md.append("| Rank | Run | Score | Delta | Metric (Score + Delta) |")
output_md.append("|:---:|---|:---:|:---:|:---:|")

# Sort for Gemini
gemini_sorted = sorted(data, key=lambda x: x['gemini_metric'] if x['gemini_score'] else -1000, reverse=True)
for i, d in enumerate(gemini_sorted):
    output_md.append(f"| {i+1} | {d['run']} | {format_val(d['gemini_score'])} | {format_val(d['gemini_delta'], True)} | {format_val(d['gemini_metric'])} |")

# --- CEREBRAS SECTION ---
output_md.append("")
output_md.append("### Cerebras Rankings")
output_md.append("Rank calculated using the equation: `Score + Delta`")
output_md.append("")
output_md.append("| Rank | Run | Score | Delta | Metric (Score + Delta) |")
output_md.append("|:---:|---|:---:|:---:|:---:|")

cerebras_sorted = sorted(data, key=lambda x: x['cerebras_metric'] if x['cerebras_score'] else -1000, reverse=True)
for i, d in enumerate(cerebras_sorted):
    output_md.append(f"| {i+1} | {d['run']} | {format_val(d['cerebras_score'])} | {format_val(d['cerebras_delta'], True)} | {format_val(d['cerebras_metric'])} |")


with open(r"D:\HOM-LLM(v2.0)\eval_rankings.md", "w") as f:
    f.write("\n".join(output_md))
print("Done writing to eval_rankings.md")
