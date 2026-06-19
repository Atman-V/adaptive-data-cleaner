"""
etl/encoding_helper.py
Auto-detects CSV file encoding to handle Excel-exported, Windows-1252,
Latin-1, ISO-8859-1, etc. — not just UTF-8.
"""

import codecs

# Order matters: try the strictest / most common first.
ENCODINGS_TO_TRY = [
    "utf-8-sig",     # UTF-8 with BOM (common Excel export)
    "utf-8",         # plain UTF-8
    "utf-16",        # UTF-16 with BOM
    "cp1252",        # Windows-1252 (most common Excel for English/Western Europe)
    "iso-8859-1",    # Latin-1 (Western European)
    "iso-8859-15",   # Latin-9 (adds €)
    "cp1250",        # Windows Central European
    "cp1251",        # Windows Cyrillic
    "shift_jis",     # Japanese
    "gb18030",       # Chinese
    "latin-1",       # Fallback — accepts any byte
]


def detect_encoding(filepath, sample_size=65536):
    """
    Try opening the file with each candidate encoding and return the first
    one that decodes a sample without errors.

    Args:
        filepath:    path to the CSV file
        sample_size: bytes to read for the test (default 64KB)

    Returns:
        encoding name string. Falls back to 'latin-1' which never fails
        (it accepts any single-byte input).
    """
    # Read raw bytes once
    with open(filepath, "rb") as f:
        raw = f.read(sample_size)

    # Quick BOM check first — most reliable
    if raw.startswith(codecs.BOM_UTF8):    return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE): return "utf-16"
    if raw.startswith(codecs.BOM_UTF16_BE): return "utf-16"

    # Try each encoding strict
    for enc in ENCODINGS_TO_TRY:
        try:
            raw.decode(enc, errors="strict")
            return enc
        except (UnicodeDecodeError, LookupError):
            continue

    return "latin-1"   # Absolute fallback — always decodes


def open_csv(filepath, mode="r"):
    """
    Open a CSV file with auto-detected encoding.

    Returns an open file object ready to read.
    """
    enc = detect_encoding(filepath)
    return open(filepath, mode, newline="", encoding=enc, errors="replace")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m etl.encoding_helper <file.csv>")
        sys.exit(1)
    enc = detect_encoding(sys.argv[1])
    print(f"Detected encoding: {enc}")
    # Show first 3 lines as a sanity check
    with open_csv(sys.argv[1]) as f:
        for i, line in enumerate(f):
            if i >= 3: break
            print(f"  line {i+1}: {line.rstrip()[:200]}")
