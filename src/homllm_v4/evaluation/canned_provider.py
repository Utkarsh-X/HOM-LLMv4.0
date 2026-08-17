"""Canned provider content for deterministic (fake) edit providers.

Used only for regression and safety tests, never for live benchmarking.
The content mapping mirrors the fixture bugs in ``test_repo`` so a fake
provider can propose the exact fix each benchmark case expects.

For external SWE-bench fixtures, ``provider_mode="swebench_gold"`` applies
the fixture's gold patch (from its manifest) to the current content, so the
whole external suite is regression-runnable headlessly -- the harness then
proves the full loop (index, patch, hidden-test verify, rollback, gate)
without spending tokens on a live model.
"""

from __future__ import annotations

import json

from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalResponse,
)
from homllm_v4.utils.unified_diff import apply_unified_diff


def canned_provider_content(
    *,
    provider_mode: str,
    target_content: str,
    gold_patch: str | None = None,
) -> str:
    """Return the fixed file content a deterministic provider would propose.

    Raises ``ValueError`` when the expected buggy pattern is not present, so a
    fixture/case mismatch fails loudly instead of silently passing.

    ``gold_patch`` is required for ``provider_mode="swebench_gold"`` and is
    ignored otherwise.
    """
    if provider_mode == "truncate_guard":
        old = (
            "    if len(text) <= max_length:\n"
            "        return text\n"
            "    return text[:max_length - len(suffix)] + suffix"
        )
        new = (
            "    if len(text) <= max_length:\n"
            "        return text\n"
            "    if max_length <= len(suffix):\n"
            "        return text[:max_length]\n"
            "    return text[:max_length - len(suffix)] + suffix"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "file_path_drive_guard":
        old = (
            "    if '..' in file_path or file_path.startswith('/'):\n"
            "        return False, \"Invalid file path\""
        )
        new = (
            "    if '..' in file_path or file_path.startswith('/') "
            "or file_path.startswith('\\\\') or ':' in file_path:\n"
            "        return False, \"Invalid file path\""
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "email_local_dot_guard":
        old = (
            "    if not re.match(email_pattern, email):\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    return True, None"
        )
        new = (
            "    if not re.match(email_pattern, email):\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    local_part = email.split('@', 1)[0]\n"
            "    if '..' in local_part:\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    return True, None"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "parse_date_strip":
        old = "        return datetime.strptime(date_string, format_str)"
        new = "        return datetime.strptime(date_string.strip(), format_str)"
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "job_queue_size_guard":
        old = (
            "            if len(self.pending_jobs) >= self.max_queue_size:\n"
            "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
        )
        new = (
            "            current_queue_size = sum(len(jobs) for jobs in self.pending_jobs.values())\n"
            "            if current_queue_size >= self.max_queue_size:\n"
            "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "cache_namespace_invalidation":
        old = "        return hashlib.md5(key.encode()).hexdigest()"
        new = "        return key"
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "metrics_labelled_stats":
        old = (
            "    def get_all_metrics(self) -> Dict[str, Any]:\n"
            "        \"\"\"Get all collected metrics.\"\"\"\n"
            "        return {\n"
            "            \"counters\": dict(self.counters),\n"
            "            \"gauges\": dict(self.gauges),\n"
            "            \"histogram_stats\": {\n"
            "                key: self.get_histogram_stats(key.split(\"{\")[0])\n"
            "                for key in self.histograms.keys()\n"
            "            },\n"
            "            \"timer_stats\": {\n"
            "                key: self.get_timer_stats(key.split(\"{\")[0])\n"
            "                for key in self.timers.keys()\n"
            "            }\n"
            "        }"
        )
        new = (
            "    def get_all_metrics(self) -> Dict[str, Any]:\n"
            "        \"\"\"Get all collected metrics.\"\"\"\n"
            "        def value_stats(values: List[float]) -> Dict[str, float]:\n"
            "            if not values:\n"
            "                return {}\n"
            "            sorted_values = sorted(values)\n"
            "            return {\n"
            "                \"count\": len(values),\n"
            "                \"sum\": sum(values),\n"
            "                \"mean\": sum(values) / len(values),\n"
            "                \"min\": min(values),\n"
            "                \"max\": max(values),\n"
            "                \"p50\": sorted_values[len(values) // 2],\n"
            "                \"p95\": sorted_values[int(len(values) * 0.95)],\n"
            "                \"p99\": sorted_values[int(len(values) * 0.99)]\n"
            "            }\n"
            "        return {\n"
            "            \"counters\": dict(self.counters),\n"
            "            \"gauges\": dict(self.gauges),\n"
            "            \"histogram_stats\": {\n"
            "                key: value_stats(values)\n"
            "                for key, values in self.histograms.items()\n"
            "            },\n"
            "            \"timer_stats\": {\n"
            "                key: value_stats(values)\n"
            "                for key, values in self.timers.items()\n"
            "            }\n"
            "        }"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "inventory_sku_strip_normalization":
        old = "    return sku.upper()"
        new = "    return sku.strip().upper()"
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "pricing_negative_discount_guard":
        old = "    return price * rate"
        new = (
            "    if rate < 0:\n"
            "        return 0.0\n"
            "    return price * rate"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "hashing_needs_rehash":
        old = (
            "    # Simplified: always return False for this implementation\n"
            "    # In production, would check if hash uses current BCRYPT_ROUNDS\n"
            "    return False"
        )
        new = (
            "    # Legacy unsalted hashes (no colon separator) always need rehashing.\n"
            "    if \":\" not in hashed:\n"
            "        return True\n"
            "    salt = hashed.split(\":\", 1)[0]\n"
            "    # Salt below the current bcrypt-equivalent cost (16 hex chars = 64 bits)\n"
            "    # indicates the hash was generated with older, weaker parameters.\n"
            "    return len(salt) < 16"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "filters_anonymous_public":
        old = (
            "        if user_id:\n"
            "            # Users can access files in their user directory\n"
            "            if f\"/{user_id}/\" in file_path or f\"\\\\{user_id}\\\\\" in file_path:\n"
            "                has_access = True\n"
            "            # Public files are accessible to all\n"
            "            elif \"/public/\" in file_path or \"\\\\public\\\\\" in file_path:\n"
            "                has_access = True"
        )
        new = (
            "        # Public files are accessible to all users, including anonymous\n"
            "        if \"/public/\" in file_path or \"\\\\public\\\\\" in file_path:\n"
            "            has_access = True\n"
            "        elif user_id:\n"
            "            # Users can access files in their user directory\n"
            "            if f\"/{user_id}/\" in file_path or f\"\\\\{user_id}\\\\\" in file_path:\n"
            "                has_access = True"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "query_optimizer_pushdown":
        old = (
            "        # Reorder filters by selectivity (most selective first)\n"
            "        ops.filters.sort(\n"
            "            key=lambda f: self._estimate_selectivity(f),\n"
            "            reverse=True\n"
            "        )"
        )
        new = (
            "        # Reorder filters by selectivity (most selective first)\n"
            "        ops.filters.sort(\n"
            "            key=lambda f: self._estimate_selectivity(f)\n"
            "        )"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "redis_pickle_hit_stats":
        old = (
            "                if pkl_value:\n"
            "                    value = pickle.loads(pkl_value)\n"
            "                    self._misses += 1\n"
            "                    return value"
        )
        new = (
            "                if pkl_value:\n"
            "                    value = pickle.loads(pkl_value)\n"
            "                    self._hits += 1\n"
            "                    return value"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "query_planner_param_cache":
        old = (
            "        # Generate cache key\n"
            "        cache_key = self._make_cache_key(query)"
        )
        new = (
            "        # Generate cache key (parameters affect the plan, so they must be in the key)\n"
            "        cache_key = self._make_cache_key(query, parameters)"
        )
        target_content = _replace_or_raise(provider_mode, target_content, old, new)
        old = (
            "    def _make_cache_key(self, query: str) -> str:\n"
            "        \"\"\"Generate cache key for query.\"\"\"\n"
            "        import hashlib\n"
            "        return hashlib.md5(query.encode()).hexdigest()"
        )
        new = (
            "    def _make_cache_key(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> str:\n"
            "        \"\"\"Generate cache key for query and parameters.\"\"\"\n"
            "        import hashlib\n"
            "        import json\n"
            "        params_json = json.dumps(parameters, sort_keys=True, default=str) if parameters else \"\"\n"
            "        return hashlib.md5(f\"{query}|{params_json}\".encode()).hexdigest()"
        )
        return _replace_or_raise(provider_mode, target_content, old, new)
    if provider_mode == "noop":
        return target_content
    if provider_mode == "swebench_gold":
        if not gold_patch:
            raise ValueError("swebench_gold_requires_gold_patch")
        return apply_unified_diff(target_content, gold_patch)
    raise ValueError(f"unsupported_provider_mode: {provider_mode}")


class PromptAwareCannedProvider:
    """Deterministic edit provider that proposes a canned fix.

    Fully prompt-driven: the target file, evidence ids, and current content are
    all parsed from the proposal prompt, so the same instance works for
    supplied-target and target-selection cases. The ``new_content`` is derived
    from the current content by applying the canned fix for ``provider_mode``.
    """

    tokens_in = 1
    tokens_out = 1

    def __init__(
        self,
        *,
        provider_mode: str,
        target_file: str | None = None,
        gold_patch: str | None = None,
    ) -> None:
        self.provider_mode = provider_mode
        self.target_file = target_file
        self.gold_patch = gold_patch

    def propose_edit(self, request) -> ProviderEditProposalResponse:
        evidence_ids: tuple[str, ...] = ()
        target_file = self.target_file
        current_content = ""
        in_current_content = False
        for line in request.prompt.splitlines():
            if in_current_content:
                current_content += line + "\n"
                continue
            if line.startswith("Evidence IDs:"):
                evidence_ids = tuple(
                    item.strip()
                    for item in line.removeprefix("Evidence IDs:").split(",")
                    if item.strip()
                )
            elif line.startswith("Target file: "):
                target_file = line.removeprefix("Target file: ").strip()
            elif line == "Current content:":
                in_current_content = True
        new_content = canned_provider_content(
            provider_mode=self.provider_mode,
            target_content=current_content,
            gold_patch=self.gold_patch,
        )
        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": target_file,
                    "new_content": new_content,
                    "rationale": "Deterministic canned provider proposal.",
                    "evidence_ids": list(evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            model="canned-provider",
            metadata={"provider": "canned-regression"},
        )


def _replace_or_raise(
    provider_mode: str,
    target_content: str,
    old: str,
    new: str,
) -> str:
    if old not in target_content:
        raise ValueError(f"{provider_mode}_pattern_not_found")
    return target_content.replace(old, new)
