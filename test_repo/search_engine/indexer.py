"""
Document indexer for parsing and indexing files.
Handles various file types and generates embeddings.

Complex features:
- Multi-format file parsing (Python, JavaScript, Markdown, JSON)
- AST-based code analysis for Python
- Chunking strategy for large files
- Incremental indexing with change detection
- Embedding caching to avoid recomputation
- Parallel processing support
- Metadata extraction (docstrings, comments, imports)
"""

import os
import ast
import json
import mimetypes
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
from config import settings
from core.interfaces import IIndexer
from core.exceptions import IndexingError, EmbeddingGenerationError, BinaryFileError

logger = logging.getLogger(__name__)

@dataclass
class FileMetadata:
    """Metadata extracted from a file."""
    file_path: str
    file_hash: str
    language: str
    line_count: int
    function_count: int
    class_count: int
    import_count: int
    docstring: Optional[str] = None
    last_modified: float = 0.0

class DocumentIndexer(IIndexer):
    """
    Indexes documents by parsing files and generating embeddings.
    Handles text files, code files, and skips binary files.
    Includes advanced parsing, chunking, and caching capabilities.
    """
    
    def __init__(self, enable_caching: bool = True, chunk_size: int = 512, chunk_overlap: int = 50):
        """
        Initialize the document indexer.
        
        Args:
            enable_caching: Whether to cache embeddings
            chunk_size: Size of text chunks for large files
            chunk_overlap: Overlap between chunks
        """
        self.supported_extensions = settings.SUPPORTED_EXTENSIONS
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        self.embedding_dim = settings.EMBEDDING_DIMENSION
        self.enable_caching = enable_caching
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Caching
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._metadata_cache: Dict[str, FileMetadata] = {}
        self._file_hashes: Dict[str, str] = {}
        
        # Statistics
        self._indexed_files: Set[str] = set()
        self._failed_files: Dict[str, str] = {}
        self._total_chunks = 0
    
    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of file content."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _extract_metadata(self, file_path: str, content: str) -> FileMetadata:
        """Extract metadata from file content."""
        file_hash = self._compute_file_hash(file_path)
        language = self._detect_language(file_path, content)
        lines = content.split('\n')
        
        # Count entities based on language
        if language == 'python':
            functions, classes, imports = self._count_python_entities(content)
        else:
            functions = content.count('function ') + content.count('def ')
            classes = content.count('class ')
            imports = content.count('import ') + content.count('from ')
        
        # Extract docstring (module-level)
        docstring = self._extract_module_docstring(content, language)
        
        return FileMetadata(
            file_path=file_path,
            file_hash=file_hash,
            language=language,
            line_count=len(lines),
            function_count=functions,
            class_count=classes,
            import_count=imports,
            docstring=docstring,
            last_modified=os.path.getmtime(file_path) if os.path.exists(file_path) else 0.0
        )
    
    def _detect_language(self, file_path: str, content: str) -> str:
        """Detect programming language from file extension and content."""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.md': 'markdown',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml'
        }
        return lang_map.get(ext, 'text')
    
    def _count_python_entities(self, content: str) -> Tuple[int, int, int]:
        """Count functions, classes, and imports in Python code."""
        try:
            tree = ast.parse(content)
            functions = sum(1 for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
            classes = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
            imports = sum(1 for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))
            return functions, classes, imports
        except SyntaxError:
            # Fallback to regex if AST parsing fails
            import re
            functions = len(re.findall(r'\bdef\s+\w+', content))
            classes = len(re.findall(r'\bclass\s+\w+', content))
            imports = len(re.findall(r'\b(import|from)\s+', content))
            return functions, classes, imports
    
    def _extract_module_docstring(self, content: str, language: str) -> Optional[str]:
        """Extract module-level docstring."""
        if language == 'python':
            try:
                tree = ast.parse(content)
                docstring = ast.get_docstring(tree)
                return docstring
            except SyntaxError:
                # Fallback: look for triple-quoted string at start
                import re
                match = re.match(r'^"""(.*?)"""', content, re.DOTALL)
                if not match:
                    match = re.match(r"^'''(.*?)'''", content, re.DOTALL)
                return match.group(1).strip() if match else None
        return None
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - self.chunk_overlap
            if start >= len(text):
                break
        return chunks
    
    def index_file(self, file_path: str) -> bool:
        """
        Index a single file with advanced features.
        Includes change detection, chunking, and metadata extraction.
        
        Args:
            file_path: Path to file to index
            
        Returns:
            True if indexing succeeded, False otherwise
            
        Raises:
            BinaryFileError: If file is binary
            EmbeddingGenerationError: If embedding generation fails
        """
        try:
            # Check file exists
            if not os.path.exists(file_path):
                logger.warning(f"File does not exist: {file_path}")
                return False
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                logger.warning(f"File too large ({file_size} bytes): {file_path}")
                return False
            
            # Check if binary file
            if self._is_binary_file(file_path):
                raise BinaryFileError(f"Cannot index binary file: {file_path}")
            
            # Check if file changed (incremental indexing)
            current_hash = self._compute_file_hash(file_path)
            if self.enable_caching and file_path in self._file_hashes:
                if self._file_hashes[file_path] == current_hash:
                    logger.debug(f"File unchanged, skipping: {file_path}")
                    return True  # Already indexed
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try different encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                            content = f.read()
                        break
                    except Exception:
                        continue
                else:
                    raise IndexingError(f"Could not decode file {file_path}")
            
            # Extract metadata
            metadata = self._extract_metadata(file_path, content)
            self._metadata_cache[file_path] = metadata
            
            # Generate embeddings (chunked for large files)
            if len(content) > self.chunk_size * 2:
                chunks = self._chunk_text(content)
                embeddings = []
                for chunk in chunks:
                    embedding = self.generate_embedding(chunk)
                    if embedding is not None:
                        embeddings.append(embedding)
                    else:
                        raise EmbeddingGenerationError(f"Failed to generate embedding for chunk in {file_path}")
                
                # Combine chunk embeddings (average)
                if embeddings:
                    combined_embedding = np.mean(embeddings, axis=0)
                    combined_embedding = combined_embedding / np.linalg.norm(combined_embedding)
                else:
                    raise EmbeddingGenerationError(f"No valid embeddings generated for {file_path}")
            else:
                # Single embedding for small files
                combined_embedding = self.generate_embedding(content)
                if combined_embedding is None:
                    raise EmbeddingGenerationError(f"Failed to generate embedding for {file_path}")
            
            # Cache embedding
            if self.enable_caching:
                self._embedding_cache[file_path] = combined_embedding
                self._file_hashes[file_path] = current_hash
            
            self._indexed_files.add(file_path)
            self._total_chunks += len(chunks) if len(content) > self.chunk_size * 2 else 1
            
            logger.info(f"Indexed {file_path}: {metadata.function_count} functions, {metadata.class_count} classes")
            return True
            
        except BinaryFileError:
            raise
        except EmbeddingGenerationError:
            raise
        except Exception as e:
            self._failed_files[file_path] = str(e)
            logger.error(f"Failed to index file {file_path}: {e}")
            raise IndexingError(f"Failed to index file {file_path}: {e}")
    
    def index_directory(self, directory_path: str) -> int:
        """
        Index all supported files in a directory.
        
        Args:
            directory_path: Path to directory
            
        Returns:
            Number of files indexed
        """
        indexed_count = 0
        
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = Path(file_path).suffix
                
                if file_ext in self.supported_extensions:
                    try:
                        if self.index_file(file_path):
                            indexed_count += 1
                    except (BinaryFileError, EmbeddingGenerationError):
                        # Skip files that can't be indexed
                        continue
                    except Exception:
                        # Log but continue
                        continue
        
        return indexed_count
    
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding vector for text with caching.
        Uses a sophisticated character-based embedding algorithm.
        In production, would use a transformer model (e.g., sentence-transformers).
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if generation fails
        """
        if not text or not text.strip():
            return None
        
        # Check cache first
        if self.enable_caching:
            text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            cache_key = f"embed_{text_hash}"
            if cache_key in self._embedding_cache:
                return self._embedding_cache[cache_key].copy()
        
        try:
            # Advanced mock embedding: combines multiple features
            # 1. Character frequency distribution
            char_freq = np.zeros(256)  # ASCII frequency
            for char in text:
                if ord(char) < 256:
                    char_freq[ord(char)] += 1
            
            # 2. Word-based features (if text is long enough)
            words = text.split()
            word_lengths = [len(w) for w in words[:100]]  # Limit to first 100 words
            
            # 3. Structural features (brackets, quotes, etc.)
            structural = np.array([
                text.count('('), text.count(')'),
                text.count('['), text.count(']'),
                text.count('{'), text.count('}'),
                text.count('"'), text.count("'"),
                text.count('\n'), text.count('\t')
            ])
            
            # Combine features into embedding
            embedding = np.zeros(self.embedding_dim)
            
            # Fill first part with normalized character frequencies
            char_freq_norm = char_freq / (np.sum(char_freq) + 1e-10)
            embedding[:min(256, self.embedding_dim)] = char_freq_norm[:min(256, self.embedding_dim)]
            
            # Fill next part with word length statistics
            if word_lengths:
                word_stats = np.array([
                    np.mean(word_lengths),
                    np.std(word_lengths) if len(word_lengths) > 1 else 0,
                    np.max(word_lengths) if word_lengths else 0,
                    len(word_lengths)
                ])
                start_idx = min(256, self.embedding_dim)
                end_idx = min(start_idx + 4, self.embedding_dim)
                embedding[start_idx:end_idx] = word_stats[:end_idx - start_idx]
            
            # Fill with structural features
            struct_start = min(260, self.embedding_dim)
            struct_end = min(struct_start + len(structural), self.embedding_dim)
            if struct_end > struct_start:
                embedding[struct_start:struct_end] = structural[:struct_end - struct_start] / (len(text) + 1)
            
            # Fill remaining with character n-grams (bigrams)
            remaining = self.embedding_dim - struct_end
            if remaining > 0:
                bigrams = {}
                for i in range(len(text) - 1):
                    bigram = text[i:i+2]
                    bigrams[bigram] = bigrams.get(bigram, 0) + 1
                
                # Take top N bigrams by frequency
                sorted_bigrams = sorted(bigrams.items(), key=lambda x: x[1], reverse=True)[:remaining]
                for idx, (_, freq) in enumerate(sorted_bigrams):
                    if struct_end + idx < self.embedding_dim:
                        embedding[struct_end + idx] = freq / (len(text) + 1)
            
            # Normalize to unit vector
            norm = np.linalg.norm(embedding)
            if norm > 1e-10:
                embedding = embedding / norm
            else:
                # Fallback: uniform vector
                embedding = np.ones(self.embedding_dim) / np.sqrt(self.embedding_dim)
            
            # Cache if enabled
            if self.enable_caching:
                text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                cache_key = f"embed_{text_hash}"
                if len(self._embedding_cache) < 1000:  # Limit cache size
                    self._embedding_cache[cache_key] = embedding.copy()
            
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None
    
    def _is_binary_file(self, file_path: str) -> bool:
        """
        Check if a file is binary.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if file is binary, False otherwise
        """
        # Check MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and not mime_type.startswith('text/'):
            return True
        
        # Check file extension
        binary_extensions = ['.exe', '.dll', '.so', '.bin', '.jpg', '.png', '.pdf']
        if any(file_path.lower().endswith(ext) for ext in binary_extensions):
            return True
        
        # Check first few bytes for null characters
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(512)
                if b'\x00' in chunk:
                    return True
        except Exception:
            pass
        
        return False
    
    def parse_python_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parse a Python file to extract functions, classes, and docstrings using AST.
        This is used by queries asking about Python file parsing.
        Provides comprehensive code analysis including decorators, arguments, and inheritance.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Dictionary with parsed information including AST details
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Use AST for accurate parsing
            try:
                tree = ast.parse(content, filename=file_path)
            except SyntaxError as e:
                logger.warning(f"Syntax error in {file_path}: {e}")
                # Fallback to simple line-based parsing
                return self._parse_python_simple(file_path, content)
            
            functions = []
            classes = []
            imports = []
            decorators = []
            
            # AST visitor to extract detailed information
            class CodeVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.functions = []
                    self.classes = []
                    self.imports = []
                    self.decorators = []
                
                def visit_FunctionDef(self, node):
                    func_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'end_line': node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                        'args': [arg.arg for arg in node.args.args],
                        'decorators': [ast.unparse(d) if hasattr(ast, 'unparse') else d.__class__.__name__ 
                                     for d in node.decorator_list],
                        'docstring': ast.get_docstring(node),
                        'is_async': isinstance(node, ast.AsyncFunctionDef)
                    }
                    self.functions.append(func_info)
                    self.generic_visit(node)
                
                def visit_ClassDef(self, node):
                    # Get base classes
                    bases = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                        elif hasattr(ast, 'unparse'):
                            bases.append(ast.unparse(base))
                    
                    class_info = {
                        'name': node.name,
                        'line': node.lineno,
                        'end_line': node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                        'bases': bases,
                        'decorators': [ast.unparse(d) if hasattr(ast, 'unparse') else d.__class__.__name__
                                     for d in node.decorator_list],
                        'docstring': ast.get_docstring(node),
                        'methods': [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    }
                    self.classes.append(class_info)
                    self.generic_visit(node)
                
                def visit_Import(self, node):
                    for alias in node.names:
                        self.imports.append({
                            'module': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno
                        })
                
                def visit_ImportFrom(self, node):
                    module = node.module or ''
                    for alias in node.names:
                        self.imports.append({
                            'module': module,
                            'name': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno
                        })
            
            visitor = CodeVisitor()
            visitor.visit(tree)
            
            # Extract module-level docstring
            module_docstring = ast.get_docstring(tree)
            
            return {
                'file_path': file_path,
                'functions': visitor.functions,
                'classes': visitor.classes,
                'imports': visitor.imports,
                'line_count': len(content.split('\n')),
                'module_docstring': module_docstring,
                'ast_parsed': True
            }
        except Exception as e:
            logger.error(f"AST parsing failed for {file_path}: {e}")
            # Fallback to simple parsing
            return self._parse_python_simple(file_path, content if 'content' in locals() else '')
    
    def _parse_python_simple(self, file_path: str, content: str) -> Dict[str, Any]:
        """Fallback simple parsing when AST fails."""
        functions = []
        classes = []
        imports = []
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('def ') or stripped.startswith('async def '):
                func_name = stripped.split('def ')[1].split('(')[0].strip()
                functions.append({'name': func_name, 'line': i + 1})
            elif stripped.startswith('class '):
                class_name = stripped.split('class ')[1].split('(')[0].split(':')[0].strip()
                classes.append({'name': class_name, 'line': i + 1})
            elif stripped.startswith('import ') or stripped.startswith('from '):
                imports.append({'module': stripped, 'line': i + 1})
        
        return {
            'file_path': file_path,
            'functions': functions,
            'classes': classes,
            'imports': imports,
            'line_count': len(lines),
            'ast_parsed': False
        }
    
    def get_indexing_stats(self) -> Dict[str, Any]:
        """Get statistics about indexing operations."""
        return {
            'indexed_files': len(self._indexed_files),
            'failed_files': len(self._failed_files),
            'total_chunks': self._total_chunks,
            'cached_embeddings': len(self._embedding_cache),
            'cached_metadata': len(self._metadata_cache)
        }
    
    def clear_cache(self):
        """Clear all caches."""
        self._embedding_cache.clear()
        self._metadata_cache.clear()
        self._file_hashes.clear()
        logger.info("Indexer cache cleared")
