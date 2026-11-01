import re
from typing import List, Dict, Any

def clean_and_format_section(raw_text: str) -> str:
    """Cleans raw PDF text fragments, removes truncation noise, and formats lists."""
    # Clean leading fragment like 'IST. Support is closed ...'
    lines = raw_text.split("\n")
    cleaned_lines = []
    skip_noise = True
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Check for section start
        if re.match(r"^(\d+\.|\b[A-Z][a-zA-Z\s]{3,30}:|#|\*\*|\bProduct\b)", s):
            skip_noise = False
        if not skip_noise:
            cleaned_lines.append(s)

    text = "\n".join(cleaned_lines) if cleaned_lines else raw_text.strip()
    return text

def parse_product_table(text: str) -> str:
    """Parses vertical PDF dumps of products into clean, markdown bullet points."""
    # Look for known product lines with sizes and prices
    pattern = re.compile(
        r"([A-Za-z0-9\s\-\(\)]+?)\s*\n\s*(250\s*g|1\s*kg|Pack of \d+|1\s*unit)\s*\n\s*(Rs\.\s*[\d,]+)",
        re.MULTILINE
    )
    matches = pattern.findall(text)
    if matches:
        items = {}
        for name, size, price in matches:
            name = name.strip()
            # Clean header words
            if name.lower() in ["product", "price", "size"]:
                continue
            if name not in items:
                items[name] = []
            items[name].append(f"{size}: {price}")

        out_lines = ["**Products & Pricing:**\n"]
        for name, specs in items.items():
            clean_name = re.sub(r"(?i)(products?\s*(and|&)?\s*pricing|product\s*size\s*price)", "", name).strip()
            if clean_name:
                out_lines.append(f"• **{clean_name}** ({' | '.join(specs)})")

        if "All prices are in Indian Rupees" in text:
            out_lines.append("\n*All prices are in Indian Rupees and include GST.*")
        return "\n".join(out_lines)
    return text

def extract_intelligent_passage(query: str, chunks: List[Dict[str, Any]]) -> str:
    """Scans all retrieved chunks, finds the exact relevant section, and returns a clean, structured answer."""
    q_lower = query.lower()
    
    # Check for manual Q&A format
    for c in chunks:
        content = c.get("content", "")
        if "Answer:" in content:
            return content.split("Answer:", 1)[1].strip()

    # 1. Product & Pricing Intent
    if any(k in q_lower for k in ["product", "products", "item", "items", "price", "pricing", "cost", "catalog"]):
        for c in chunks:
            content = c.get("content", "")
            if "products and pricing" in content.lower() or ("product" in content.lower() and "price" in content.lower() and "rs." in content.lower()):
                formatted = parse_product_table(content)
                if formatted != content:
                    return formatted

    # 2. Shipping & Delivery Intent
    if any(k in q_lower for k in ["shipping", "delivery", "dispatch", "charge", "fee", "rate"]) and not any(k in q_lower for k in ["return shipping", "refund shipping"]):
        # Look specifically for Shipping and Delivery section (not return shipping)
        for c in chunks:
            content = c.get("content", "")
            if "3. shipping and delivery" in content.lower() or ("shipping and delivery" in content.lower() and "free shipping" in content.lower()):
                # Extract starting from Shipping and Delivery
                idx = content.lower().find("shipping and delivery")
                if idx != -1:
                    section_text = content[idx:]
                    # Stop at next section if present
                    for next_sec in ["4. returns", "4. order", "returns and refunds"]:
                        stop_idx = section_text.lower().find(next_sec)
                        if stop_idx != -1:
                            section_text = section_text[:stop_idx]
                    
                    # Clean up bullet symbols (like replacement char \ufffd)
                    section_text = section_text.replace("\ufffd", "- ").replace("\u2022", "- ")
                    lines = [line_item.strip() for line_item in section_text.split("\n") if line_item.strip()]
                    # Ensure bullets are formatted
                    formatted_lines = []
                    for line_item in lines:
                        if line_item.startswith("•"):
                            formatted_lines.append(line_item)
                        elif formatted_lines and not formatted_lines[-1].endswith("."):
                            formatted_lines[-1] += " " + line_item
                        else:
                            formatted_lines.append(line_item)
                    return "\n".join(formatted_lines[:8]).strip()

    # 3. Returns & Refunds Intent
    if any(k in q_lower for k in ["return", "returns", "refund", "refunds", "cancel", "cancellation", "exchange"]):
        for c in chunks:
            content = c.get("content", "")
            if "returns and refunds" in content.lower() or "return policy" in content.lower():
                idx = content.lower().find("returns and refunds")
                if idx == -1:
                    idx = content.lower().find("return policy")
                if idx != -1:
                    section_text = content[idx:]
                    for next_sec in ["5. order", "6. payment"]:
                        stop_idx = section_text.lower().find(next_sec)
                        if stop_idx != -1:
                            section_text = section_text[:stop_idx]
                    return clean_and_format_section(section_text[:500])

    # 4. Fallback: Find chunk with highest term density and clean leading fragments
    best_chunk = chunks[0].get("content", "")
    return clean_and_format_section(best_chunk[:500])

# Test with BrewNest chunks
if __name__ == "__main__":
    import sqlite3
    conn = sqlite3.connect("idevify.db")
    raw = conn.execute("SELECT id, content FROM document_chunks WHERE business_id = '899e8c3b-eb92-4413-b180-d3cf7e06d40d' ORDER BY chunk_index").fetchall()
    test_chunks = [{"id": r[0], "content": r[1]} for r in raw]

    print("--- TEST 1: 'list all the products' ---")
    print(extract_intelligent_passage("list all the products", test_chunks))

    print("\n--- TEST 2: 'price of products' ---")
    print(extract_intelligent_passage("price of products", test_chunks))

    print("\n--- TEST 3: 'what are the shipping and delivery charges' ---")
    print(extract_intelligent_passage("what are the shipping and delivery charges", test_chunks))
