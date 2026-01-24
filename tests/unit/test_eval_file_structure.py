"""
Regression tests for evaluation file structure.

Verifies:
1. No files are written to eval/generated_answers/
2. All answers appear under the correct run folder (eval/runs/<run_name>/generated_answers/)
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_no_files_written_to_top_level_generated_answers():
    """Verify persist_answer_txt does NOT write to eval/generated_answers/"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from eval.run_experiment import persist_answer_txt, ensure_dir
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir(parents=True)
        
        # Create a mock top-level generated_answers folder to ensure nothing goes there
        top_level_answers = Path(tmpdir) / "eval" / "generated_answers"
        top_level_answers.mkdir(parents=True)
        
        response = {
            "query_id": 1,
            "run_id": "test123",
            "model_name": "test-model",
            "provider": "test-provider",
            "status": "OK",
        }
        
        persist_answer_txt(response, "Test answer content", run_dir)
        
        # Verify nothing was written to top-level
        top_level_files = list(top_level_answers.iterdir())
        assert len(top_level_files) == 0, f"Files found in top-level generated_answers: {top_level_files}"


def test_answers_written_to_run_directory():
    """Verify persist_answer_txt writes to run_dir/generated_answers/"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from eval.run_experiment import persist_answer_txt
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run_20260124_123456"
        run_dir.mkdir(parents=True)
        
        response = {
            "query_id": 5,
            "run_id": "abc123",
            "model_name": "gemini-2.5-flash",
            "provider": "gemini",
            "status": "OK",
        }
        
        persist_answer_txt(response, "Test answer for query 5", run_dir)
        
        # Verify file is in run_dir/generated_answers/
        expected_path = run_dir / "generated_answers" / "query_05.txt"
        assert expected_path.exists(), f"Answer file not found at {expected_path}"
        
        # Verify content
        content = expected_path.read_text()
        assert "QUERY_ID   : 05" in content
        assert "RUN_ID     : abc123" in content
        assert "MODEL      : gemini-2.5-flash" in content
        assert "Test answer for query 5" in content


def test_multiple_queries_in_same_run():
    """Verify multiple query answers are stored in the same run folder."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from eval.run_experiment import persist_answer_txt
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run_test"
        run_dir.mkdir(parents=True)
        
        for qid in [1, 2, 3]:
            response = {
                "query_id": qid,
                "run_id": f"run_{qid}",
                "model_name": "test-model",
                "provider": "test-provider",
                "status": "OK",
            }
            persist_answer_txt(response, f"Answer for query {qid}", run_dir)
        
        answers_dir = run_dir / "generated_answers"
        answer_files = list(answers_dir.iterdir())
        
        assert len(answer_files) == 3, f"Expected 3 files, got {len(answer_files)}"
        
        expected_names = {"query_01.txt", "query_02.txt", "query_03.txt"}
        actual_names = {f.name for f in answer_files}
        assert actual_names == expected_names, f"Expected {expected_names}, got {actual_names}"
