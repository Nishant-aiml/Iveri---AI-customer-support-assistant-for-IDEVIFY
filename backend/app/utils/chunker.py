import re
from typing import List

def recursive_chunk_text(
    text: str, 
    chunk_size: int = 600, 
    overlap: int = 60
) -> List[str]:
    """Recursively splits text into readable chunks respecting natural sentence and paragraph boundaries.
    
    Args:
        text: Input string
        chunk_size: Target character length per chunk (~100-150 words)
        overlap: Character overlap between consecutive chunks
        
    Returns:
        List[str]: List of clean chunk strings
    """
    if not text or not text.strip():
        return []

    text = re.sub(r"\r\n", "\n", text).strip()
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "]
    
    def split_recursive(content: str, sep_index: int) -> List[str]:
        if len(content) <= chunk_size or sep_index >= len(separators):
            return [content.strip()] if content.strip() else []

        sep = separators[sep_index]
        splits = content.split(sep)
        chunks: List[str] = []
        current = ""

        for part in splits:
            candidate = f"{current}{sep}{part}" if current else part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current.strip())
                # If part alone is already larger than chunk_size, split further down
                if len(part) > chunk_size:
                    sub_chunks = split_recursive(part, sep_index + 1)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks

    raw_chunks = split_recursive(text, 0)
    if not raw_chunks:
        return []

    # Apply overlap smoothing across consecutive chunks
    if overlap <= 0 or len(raw_chunks) <= 1:
        return raw_chunks

    final_chunks: List[str] = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        prev_chunk = raw_chunks[i - 1]
        curr_chunk = raw_chunks[i]
        
        # Take the tail of the previous chunk as prefix
        overlap_prefix = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
        # Avoid creating a cut in the middle of a word
        space_idx = overlap_prefix.find(" ")
        if space_idx != -1 and space_idx < len(overlap_prefix) - 5:
            overlap_prefix = overlap_prefix[space_idx + 1:]
            
        combined = f"{overlap_prefix} ... {curr_chunk}"
        final_chunks.append(combined)

    return final_chunks
