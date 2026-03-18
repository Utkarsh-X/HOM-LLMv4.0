from pathlib import Path

from homllm.common.key_rotation import KeyRotationManager
from homllm.generation.providers.gemini import GeminiProvider


def test_mark_current_key_exhausted_advances_slot(tmp_path: Path):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "secrets.yaml").write_text(
        "\n".join(
            [
                "api_keys:",
                "  gemini_pool:",
                "    requests_per_key: 20",
                "    keys:",
                '      - name: "k1"',
                '        key: "KEY1"',
                '      - name: "k2"',
                '        key: "KEY2"',
            ]
        ),
        encoding="utf-8",
    )

    KeyRotationManager.reset_instance()
    mgr = KeyRotationManager.instance(tmp_path)
    assert mgr.get_key() == "KEY1"
    status = mgr.mark_current_key_exhausted()
    assert status["marked_name"] == "k1"
    assert mgr.get_key() == "KEY2"
    KeyRotationManager.reset_instance()


def test_quota_exhaustion_exception_detection():
    exc = Exception(
        "429 RESOURCE_EXHAUSTED. quota exceeded for metric: "
        "generativelanguage.googleapis.com/generate_content_free_tier_requests"
    )
    assert GeminiProvider._is_quota_exhaustion_exception(exc) is True
