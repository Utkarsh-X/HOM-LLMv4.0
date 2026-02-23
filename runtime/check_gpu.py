#!/usr/bin/env python3
"""
Simple GPU availability check for HOM-LLM runtime.

Usage:
    python runtime/check_gpu.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def check_nvidia_smi() -> tuple[bool, str]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False, "nvidia-smi not found in PATH"
    try:
        result = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return False, f"nvidia-smi failed: {stderr or 'unknown error'}"
        return True, (result.stdout or "").strip() or "GPU detected"
    except Exception as exc:
        return False, f"nvidia-smi error: {exc}"


def check_torch_cuda() -> tuple[bool, str]:
    try:
        import torch
    except Exception as exc:
        return False, f"PyTorch not importable: {exc}"

    if not torch.cuda.is_available():
        return False, "torch.cuda.is_available() = False"

    try:
        device_name = torch.cuda.get_device_name(0)
        x = torch.randn(1024, device="cuda")
        y = (x * 2.0).sum().item()
        return True, f"CUDA usable on '{device_name}' (smoke result={y:.4f})"
    except Exception as exc:
        return False, f"CUDA visible but unusable: {exc}"


def main() -> int:
    print("=== HOM-LLM GPU CHECK ===")

    smi_ok, smi_msg = check_nvidia_smi()
    torch_ok, torch_msg = check_torch_cuda()

    print(f"[PHYSICAL GPU] {'YES' if smi_ok else 'NO'} - {smi_msg}")
    print(f"[PYTORCH CUDA] {'YES' if torch_ok else 'NO'} - {torch_msg}")

    if smi_ok and torch_ok:
        print("GPU is physically present and usable by PyTorch.")
        return 0

    print("GPU is not fully usable; runtime will fall back to CPU when needed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
