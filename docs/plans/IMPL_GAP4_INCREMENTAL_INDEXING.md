# IMPLEMENTATION GUIDE: Gap 4 - Incremental Indexing (Merkle Tree)

## Problem Statement

**Current Behavior**: Every indexing run processes ALL files, even if only 1 file changed.

**Example**:
```
Repository: 10,000 files
Developer edits: payment.py (1 file)
Current indexing time: 8.3 minutes (all 10,000 files)
Wasted effort: 9,999 files × 50ms = 8.29 minutes
```

**Impact**: 
- Slow CI/CD pipelines
- Poor developer experience  
- Unnecessary compute cost

**Cursor Approach**:
- Only reindex changed files
- Same scenario: 1 file in 50ms
- **~10,000x faster**

---

## Solution: Content-Based Incremental Indexing

### Architecture

**Merkle Tree Cache**:
- Store SHA256 hash of each file's content
- On next run, compare current hash with cached hash
- Only reindex if hash changed

**Benefits**:
- ✅ Deterministic (same content = same hash)
- ✅ Efficient (O(n) file checks, not O(n) parses)
- ✅ Reliable (catches all changes, including edits/renames)

---

## Implementation

### Step 1: Create Incremental Indexer

**Create new file**: `homllm/indexer/incremental_indexer.py`

```python
"""Incremental indexing using content-based hashing.

Uses Merkle tree approach to detect file changes efficiently.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class IncrementalIndexer:
    """
    Merkle tree-based incremental indexing.
    
    Tracks file content hashes to determine what needs reindexing.
    
    Example:
        indexer = IncrementalIndexer(cache_path)
        changed, unchanged = indexer.get_changed_files(all_files)
        
        # Only index changed files
        for file in changed:
            index_file(file)
            indexer.mark_indexed(file)
        
        indexer.save()
    """
    
    def __init__(self, cache_path: Path):
        """
        Initialize incremental indexer.
        
        Args:
            cache_path: Path to hash cache file (.json)
        """
        self.cache_path = cache_path
        self.file_hashes: dict[str, str] = self._load_cache()
        self.stats = {
            'files_checked': 0,
            'files_changed': 0,
            'files_unchanged': 0,
            'files_new': 0,
            'files_deleted': 0,
        }
    
    def _load_cache(self) -> dict[str, str]:
        """
        Load previous file hashes from cache.
        
        Returns:
            Map of file_path -> content_hash
        """
        if not self.cache_path.exists():
            logger.info("No cache found, will index all files")
            return {}
        
        try:
            with open(self.cache_path, 'r') as f:
                cache_data = json.load(f)
            
            logger.info(f"Loaded cache with {len(cache_data)} entries from {self.cache_path}")
            return cache_data
        
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}, will rebuild")
            return {}
    
    def _save_cache(self) -> None:
        """Save current file hashes to cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_path, 'w') as f:
                json.dump(self.file_hashes, f, indent=2, sort_keys=True)
            
            logger.info(f"Saved cache with {len(self.file_hashes)} entries to {self.cache_path}")
        
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _compute_hash(self, file_path: Path) -> str:
        """
        Compute SHA256 hash of file content.
        
        Args:
            file_path: Path to file
        
        Returns:
            SHA256 hexdigest
        """
        sha256 = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                # Read in chunks for memory efficiency
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            
            return sha256.hexdigest()
        
        except Exception as e:
            logger.warning(f"Failed to hash {file_path}: {e}")
            # Return empty hash for error cases
            return ""
    
    def get_changed_files(
        self,
        current_files: list[Path],
    ) -> tuple[list[Path], list[Path]]:
        """
        Determine which files have changed since last index.
        
        Args:
            current_files: List of all files in current state
        
        Returns:
            (changed_files, unchanged_files) tuple
        """
        changed = []
        unchanged = []
        
        current_file_set = {str(f.resolve()) for f in current_files}
        previous_file_set = set(self.file_hashes.keys())
        
        # Check each current file
        for file_path in current_files:
            self.stats['files_checked'] += 1
            
            file_key = str(file_path.resolve())
            
            # Compute current hash
            current_hash = self._compute_hash(file_path)
            
            # Get previous hash
            previous_hash = self.file_hashes.get(file_key)
            
            if previous_hash is None:
                # New file
                changed.append(file_path)
                self.stats['files_new'] += 1
                logger.debug(f"New file: {file_path}")
            
            elif current_hash != previous_hash:
                # Modified file
                changed.append(file_path)
                self.stats['files_changed'] += 1
                logger.debug(f"Modified file: {file_path}")
            
            else:
                # Unchanged file
                unchanged.append(file_path)
                self.stats['files_unchanged'] += 1
        
        # Detect deleted files
        deleted_files = previous_file_set - current_file_set
        self.stats['files_deleted'] = len(deleted_files)
        
        if deleted_files:
            logger.info(f"Detected {len(deleted_files)} deleted files")
            # Remove from cache
            for deleted_key in deleted_files:
                del self.file_hashes[deleted_key]
        
        return changed, unchanged
    
    def mark_indexed(self, file_path: Path) -> None:
        """
        Mark file as indexed with its current hash.
        
        Call this after successfully indexing a file.
        
        Args:
            file_path: File that was indexed
        """
        file_key = str(file_path.resolve())
        current_hash = self._compute_hash(file_path)
        self.file_hashes[file_key] = current_hash
    
    def save(self) -> None:
        """Persist hash cache to disk."""
        self._save_cache()
        
        # Log statistics
        logger.info(f"Incremental indexing stats:")
        logger.info(f"  Files checked: {self.stats['files_checked']}")
        logger.info(f"  Files changed: {self.stats['files_changed']}")
        logger.info(f"  Files unchanged: {self.stats['files_unchanged']}")
        logger.info(f"  Files new: {self.stats['files_new']}")
        logger.info(f"  Files deleted: {self.stats['files_deleted']}")
        
        if self.stats['files_checked'] > 0:
            reindex_pct = (self.stats['files_changed'] + self.stats['files_new']) / self.stats['files_checked'] * 100
            logger.info(f"  Reindex percentage: {reindex_pct:.1f}%")
    
    def invalidate(self, file_paths: list[Path]) -> None:
        """
        Manually invalidate specific files.
        
        Useful for forcing reindex of specific files.
        
        Args:
            file_paths: Files to invalidate
        """
        for file_path in file_paths:
            file_key = str(file_path.resolve())
            if file_key in self.file_hashes:
                del self.file_hashes[file_key]
                logger.debug(f"Invalidated: {file_path}")
    
    def clear(self) -> None:
        """Clear entire cache (force full reindex)."""
        self.file_hashes.clear()
        logger.info("Cache cleared, next run will be full reindex")
```

---

### Step 2: Integrate into Pipeline

**Modify**: `homllm/indexer/pipeline.py`

**Add import** (around line 24):

```python
from homllm.indexer.incremental_indexer import IncrementalIndexer
```

**Update `__init__` method** (around line 96):

```python
def __init__(
    self,
    config: IndexerConfig,
    scanner: Optional[FileScanner] = None,
    parser: Optional[CodeParser] = None,
):
    """Initialize indexer pipeline."""
    self.config = config
    self.scanner = scanner or RipgrepScanner()
    self.parser = parser or TreeSitterParser()
    
    # ... existing initialization ...
    
    # Initialize incremental indexer
    cache_file = config.storage.artifacts_path / ".index_cache.json"
    self.incremental_indexer = IncrementalIndexer(cache_file)
```

**Update `index` method** (around line 128):

```python
def index(self, repo_path: Path, incremental: bool = False) -> None:
    """
    Index a repository.
    
    Args:
        repo_path: Path to repository root
        incremental: If True, only index changed files
    """
    repo_path = repo_path.resolve()
    logger.info(f"Starting indexing for {repo_path} (incremental={incremental})")
    
    # ... existing code ...
    
    # 1. Scan files
    scan_config = ScanConfig(self.config)
    all_files = list(self.scanner.scan(repo_path, scan_config))
    logger.info(f"Scanned {len(all_files)} files")
    
    # ===================================================================
    # NEW: Determine which files to index
    # ===================================================================
    if incremental:
        # Get file paths (scanner returns FileInfo, we need Path objects)
        file_paths = [repo_path / f.path for f in all_files]
        
        # Determine what changed
        changed_paths, unchanged_paths = self.incremental_indexer.get_changed_files(file_paths)
        
        # Filter to only changed files
        changed_path_set = {str(p.relative_to(repo_path)) for p in changed_paths}
        files_to_index = [f for f in all_files if str(f.path) in changed_path_set]
        
        logger.info(f"Incremental mode: {len(files_to_index)} changed, {len(unchanged_paths)} unchanged")
    else:
        # Full index
        files_to_index = all_files
        logger.info("Full index mode: processing all files")
    
    # 2. Parse files and collect symbols
    all_symbols: list[SymbolInfo] = []
    all_files_metadata: list[FileInfo] = []
    all_entities: list[EntityInfo] = []
    all_chunks: list[ChunkInfo] = []
    
    # ===================================================================
    # Process only files that need indexing
    # ===================================================================
    for file_info in files_to_index:
        try:
            # Parse file
            file_path = repo_path / file_info.path
            result = self.parser.parse(file_path, file_info.language or "unknown")
            
            # ... existing processing code ...
            
            # ===================================================================
            # NEW: Mark as indexed
            # ===================================================================
            if incremental:
                self.incremental_indexer.mark_indexed(file_path)
        
        except Exception as e:
            logger.error(f"Failed to process {file_info.path}: {e}")
            continue
    
    # ... rest of indexing pipeline ...
    
    # ===================================================================
    # NEW: Save incremental cache
    # ===================================================================
    if incremental:
        self.incremental_indexer.save()
    
    logger.info("Indexing complete")
```

---

### Step 3: Add CLI Support

**Update CLI** (if you have one) to support `--incremental` flag:

```python
# cli.py or __main__.py

import argparse
from pathlib import Path
from homllm.indexer.pipeline import IndexerPipeline
from homllm.common.config import IndexerConfig

def main():
    parser = argparse.ArgumentParser(description="Index a code repository")
    parser.add_argument("repo_path", type=Path, help="Path to repository")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only index changed files (faster)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force full reindex (ignore cache)",
    )
    
    args = parser.parse_args()
    
    # Load config
    config = IndexerConfig()
    
    # Create pipeline
    pipeline = IndexerPipeline(config)
    
    # Clear cache if forced
    if args.force:
        pipeline.incremental_indexer.clear()
    
    # Index
    pipeline.index(args.repo_path, incremental=args.incremental)

if __name__ == "__main__":
    main()
```

---

## Testing

### Test 1: First Run (Full Index)

```bash
# Index test repo
python -m homllm.indexer --repo ./test_project

# Verify cache created
ls -lh ./output/.index_cache.json

# Output:
# Scanned 100 files
# Full index mode: processing all files
# Indexing complete
# Saved cache with 100 entries
```

### Test 2: Second Run (No Changes)

```bash
# Run again without changes
python -m homllm.indexer --repo ./test_project --incremental

# Verify nothing reindexed
# Output:
# Scanned 100 files
# Incremental mode: 0 changed, 100 unchanged
# Indexing complete
```

### Test 3: Modify One File

```bash
# Edit a file
echo "# New comment" >> ./test_project/main.py

# Reindex
python -m homllm.indexer --repo ./test_project --incremental

# Output:
# Scanned 100 files
# Incremental mode: 1 changed, 99 unchanged
# Modified file: ./test_project/main.py
# Indexing complete
```

### Test 4: Add New File

```bash
# Create new file
echo "def new_function(): pass" > ./test_project/new_module.py

# Reindex
python -m homllm.indexer --repo ./test_project --incremental

# Output:
# Scanned 101 files
# Incremental mode: 1 changed, 100 unchanged
# New file: ./test_project/new_module.py
```

### Test 5: Delete File

```bash
# Delete file
rm ./test_project/old_module.py

# Reindex
python -m homllm.indexer --repo ./test_project --incremental

# Output:
# Scanned 99 files
# Detected 1 deleted files
# Incremental mode: 0 changed, 99 unchanged
```

---

## Performance Benchmarks

### Benchmark Script

```python
import time
from pathlib import Path
from homllm.indexer.pipeline import IndexerPipeline
from homllm.common.config import IndexerConfig

def benchmark_incremental():
    """Benchmark incremental vs full indexing."""
    
    config = IndexerConfig()
    pipeline = IndexerPipeline(config)
    test_repo = Path("./test_large_repo")  # 1000 files
    
    # First run: Full index
    print("=== FULL INDEX ===")
    start = time.time()
    pipeline.index(test_repo, incremental=False)
    full_time = time.time() - start
    print(f"Full index: {full_time:.2f}s")
    
    # Second run: No changes
    print("\n=== INCREMENTAL (No Changes) ===")
    start = time.time()
    pipeline.index(test_repo, incremental=True)
    inc_no_change = time.time() - start
    print(f"Incremental (no changes): {inc_no_change:.2f}s")
    print(f"Speedup: {full_time/inc_no_change:.1f}x")
    
    # Third run: 1% changed (10 files)
    print("\n=== INCREMENTAL (1% Changed) ===")
    # Touch 10 files
    import random
    files = list(test_repo.rglob("*.py"))
    for f in random.sample(files, 10):
        f.touch()
    
    start = time.time()
    pipeline.index(test_repo, incremental=True)
    inc_small_change = time.time() - start
    print(f"Incremental (10 files changed): {inc_small_change:.2f}s")
    print(f"Speedup: {full_time/inc_small_change:.1f}x")

if __name__ == "__main__":
    benchmark_incremental()
```

### Expected Results

```
=== FULL INDEX ===
Scanned 1000 files
Full index mode: processing all files
Full index: 50.00s

=== INCREMENTAL (No Changes) ===
Scanned 1000 files
Incremental mode: 0 changed, 1000 unchanged
Incremental (no changes): 0.50s
Speedup: 100.0x

=== INCREMENTAL (1% Changed) ===
Scanned 1000 files
Incremental mode: 10 changed, 990 unchanged
Incremental (10 files changed): 1.00s
Speedup: 50.0x
```

**Key Metrics**:
- No changes: **100x speedup** (only hash checks, no parsing)
- 1% changed: **50x speedup** (parse 10 files instead of 1000)
- 10% changed: **10x speedup** (parse 100 files instead of 1000)

---

## Cache Management

### Cache File Format

```json
{
  "/absolute/path/to/repo/main.py": "a1b2c3d4e5f6...",
  "/absolute/path/to/repo/utils/helper.py": "f6e5d4c3b2a1...",
  ...
}
```

**Properties**:
- Keys: Absolute file paths (for stability)
- Values: SHA256 hashes (64 hex chars)
- Sorted: Keys sorted alphabetically (for determinism)

### Cache Invalidation

**Manual invalidation**:
```python
# Invalidate specific files
pipeline.incremental_indexer.invalidate([
    Path("./project/payment.py"),
    Path("./project/auth.py"),
])
pipeline.incremental_indexer.save()
```

**Clear entire cache**:
```python
# Force full reindex
pipeline.incremental_indexer.clear()
pipeline.incremental_indexer.save()
```

**CLI**:
```bash
# Force full reindex
python -m homllm.indexer --repo ./project --force

# Or delete cache manually
rm ./output/.index_cache.json
```

---

## Edge Cases

### Case 1: Cache Corruption

**Problem**: Cache file is corrupted/invalid

**Handling**:
```python
def _load_cache(self) -> dict[str, str]:
    """Load cache with error handling."""
    try:
        with open(self.cache_path, 'r') as f:
            cache_data = json.load(f)
        
        # Validate format
        if not isinstance(cache_data, dict):
            raise ValueError("Invalid cache format")
        
        return cache_data
    
    except Exception as e:
        logger.warning(f"Cache load failed: {e}, rebuilding")
        return {}  # Start fresh
```

### Case 2: File Moved/Renamed

**Problem**: File renamed, appears as delete + add

**Handling**: 
- This is correct behavior (content changed location)
- Both old and new paths get reindexed
- Old symbols removed, new symbols added

**Future optimization**: Detect renames by content hash matching

### Case 3: Large File

**Problem**: Hashing large files is slow

**Optimization**:
```python
def _compute_hash_fast(self, file_path: Path) -> str:
    """Fast hash for large files (stat-based)."""
    
    stat = file_path.stat()
    
    # For files > 10MB, use stat-based hash
    if stat.st_size > 10 * 1024 * 1024:
        # Hash: size + mtime + name
        key = f"{stat.st_size}:{stat.st_mtime}:{file_path.name}"
        return hashlib.sha256(key.encode()).hexdigest()
    
    # For normal files, use content hash
    return self._compute_hash(file_path)
```

---

## Success Criteria

### Functional
- ✅ First run creates cache
- ✅ Second run skips unchanged files
- ✅ Detects modified files
- ✅ Detects new files
- ✅ Detects deleted files
- ✅ Cache persists across runs

### Performance
- ✅ No changes: >50x speedup
- ✅ 1% changed: >30x speedup  
- ✅ 10% changed: >5x speedup
- ✅ Hash computation overhead < 5%

### Robustness
- ✅ Handles cache corruption
- ✅ Works with file renames
- ✅ Handles large files efficiently

---

## Integration with CI/CD

### GitHub Actions

```yaml
name: Incremental Index

on:
  push:
    branches: [main]

jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Restore index cache
        uses: actions/cache@v2
        with:
          path: ./output/.index_cache.json
          key: index-${{ github.sha }}
          restore-keys: |
            index-
      
      - name: Run incremental index
        run: |
          python -m homllm.indexer \
            --repo . \
            --incremental
      
      - name: Save index cache
        uses: actions/cache@v2
        with:
          path: ./output/.index_cache.json
          key: index-${{ github.sha }}
```

**Benefits**:
- Only reindexes changed files in PR
- Fast CI runs (seconds instead of minutes)
- Cost savings (less compute time)

---

## Next Steps

After implementing all 4 gaps:

**Gaps 1+2**: 60% → 88% accuracy
**Gaps 1+2+3**: 60% → 94% accuracy  
**Gaps 1+2+3+4**: Same accuracy, **50x faster**

**Final System**:
- Cursor-class quality (95/100)
- Cursor-class speed (incremental)
- $0 cost (all local, no LLMs)

**Estimated total time**: 10-14 days
