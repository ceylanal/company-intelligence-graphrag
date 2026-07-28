"""Token-aware recursive text splitter respecting paragraph and sentence boundaries."""

import hashlib
import re
from typing import NamedTuple

import tiktoken

DEFAULT_ENCODING = "cl100k_base"


class TextBlock(NamedTuple):
    text: str
    tokens: int
    page_number: int


def get_token_encoder() -> tiktoken.Encoding | None:
    """Get tiktoken encoder instance safely."""
    try:
        return tiktoken.get_encoding(DEFAULT_ENCODING)
    except Exception:
        return None


ENCODER = get_token_encoder()


def count_tokens(text: str) -> int:
    """Count tokens in text string using tiktoken or fallback estimation."""
    if not text:
        return 0
    if ENCODER is not None:
        try:
            return len(ENCODER.encode(text))
        except Exception:
            pass
    # Fallback token estimation for word-based count (~1.3 tokens per word)
    return max(1, int(len(text.split()) * 1.3))


def is_meaningful_text(text: str, min_chars: int = 15) -> bool:
    """Check if text contains meaningful content (not just punctuation or whitespace)."""
    if not text or len(text.strip()) < min_chars:
        return False
    # Ensure there is at least one alphanumeric character
    return bool(re.search(r"\w", text))


def split_text_into_blocks(page_text: str, page_number: int) -> list[TextBlock]:
    """Split page text into paragraph or sentence TextBlocks with page attribution."""
    if not page_text or not page_text.strip():
        return []

    # First split into paragraphs
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    blocks: list[TextBlock] = []

    for para in raw_paragraphs:
        para_tokens = count_tokens(para)
        # If paragraph is reasonable size (< 300 tokens), keep it intact
        if para_tokens <= 300:
            blocks.append(TextBlock(text=para, tokens=para_tokens, page_number=page_number))
        else:
            # Split large paragraph into sentences
            sentences = [s.strip() for s in re.split(r"(?<=[.!?;\n])\s+", para) if s.strip()]
            for sentence in sentences:
                sent_tokens = count_tokens(sentence)
                if sent_tokens <= 300:
                    blocks.append(TextBlock(text=sentence, tokens=sent_tokens, page_number=page_number))
                else:
                    # Split huge sentence by clause/space
                    words = sentence.split()
                    sub_chunk = ""
                    for word in words:
                        test_str = (sub_chunk + " " + word).strip()
                        if count_tokens(test_str) > 200 and sub_chunk:
                            blocks.append(
                                TextBlock(text=sub_chunk, tokens=count_tokens(sub_chunk), page_number=page_number)
                            )
                            sub_chunk = word
                        else:
                            sub_chunk = test_str
                    if sub_chunk:
                        blocks.append(
                            TextBlock(text=sub_chunk, tokens=count_tokens(sub_chunk), page_number=page_number)
                        )

    return blocks


class ChunkData(NamedTuple):
    text: str
    token_count: int
    page_number: int


def generate_chunks_from_blocks(
    blocks: list[TextBlock],
    target_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[ChunkData]:
    """Combine text blocks into chunks of approx target_tokens with overlap_tokens."""
    if not blocks:
        return []

    chunks: list[ChunkData] = []
    current_blocks: list[TextBlock] = []
    current_tokens = 0

    for block in blocks:
        # If adding block exceeds target and we already have content, emit chunk
        if current_tokens + block.tokens > target_tokens and current_blocks:
            chunk_text = "\n\n".join(b.text for b in current_blocks).strip()
            if is_meaningful_text(chunk_text):
                first_page = current_blocks[0].page_number
                chunks.append(
                    ChunkData(
                        text=chunk_text,
                        token_count=count_tokens(chunk_text),
                        page_number=first_page,
                    )
                )

            # Build overlap prefix from trailing blocks
            overlap_accum: list[TextBlock] = []
            accum_tokens = 0
            for b in reversed(current_blocks):
                if accum_tokens + b.tokens <= overlap_tokens or not overlap_accum:
                    overlap_accum.insert(0, b)
                    accum_tokens += b.tokens
                else:
                    break

            current_blocks = overlap_accum
            current_tokens = accum_tokens

        current_blocks.append(block)
        current_tokens += block.tokens

    # Emit final remaining chunk
    if current_blocks:
        chunk_text = "\n\n".join(b.text for b in current_blocks).strip()
        if is_meaningful_text(chunk_text):
            first_page = current_blocks[0].page_number
            chunks.append(
                ChunkData(
                    text=chunk_text,
                    token_count=count_tokens(chunk_text),
                    page_number=first_page,
                )
            )

    return chunks


def compute_deterministic_chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    """Generate a deterministic 16-character SHA-256 hash chunk ID."""
    raw_str = f"{document_id}:{chunk_index}:{text.strip()}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
