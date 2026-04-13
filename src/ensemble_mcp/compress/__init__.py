"""Context compression engine.

Rule-based text compression that reduces token count in natural language
while preserving all technical content (code blocks, URLs, file paths,
headings, tables). Zero LLM calls — uses compiled regex patterns and
a tokenizer-based token counter.
"""

from .engine import CompressResult, compress

__all__ = ["compress", "CompressResult"]
