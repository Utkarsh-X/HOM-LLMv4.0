from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_explain_template_prefers_material_citations_not_every_claim() -> None:
    template = (ROOT / "src" / "homllm" / "generation" / "templates" / "explain.yaml").read_text(encoding="utf-8")
    assert "material repo-grounded claims" in template
    assert "one citation per bullet or section" in template
    assert "For each factual claim, cite evidence" not in template


def test_abrm_template_prefers_material_citations_not_every_claim() -> None:
    template = (ROOT / "src" / "homllm" / "generation" / "templates" / "abrm_explain.yaml").read_text(encoding="utf-8")
    assert "material repo-grounded claims" in template
    assert "one citation per bullet or section" in template
    assert "Cite concrete evidence for each factual claim" not in template
