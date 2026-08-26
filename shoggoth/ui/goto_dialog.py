"""
Fuzzy matching used by the element picker and the command palette.

The Go-to dialog itself now lives in ``element_selector.py`` (shared with the
Insert Link action); only the scoring helper remains here because
``command_palette`` and ``element_selector`` both import it from this module.
"""


def fuzzy_match(pattern, text):
    """
    Fuzzy match pattern against text.
    Returns (match_score, matched_indices) or (0, []) if no match.

    Higher score = better match
    """
    pattern = pattern.lower()
    text = text.lower()

    if not pattern:
        return (0, [])

    # Exact match gets highest score
    if pattern in text:
        start = text.index(pattern)
        indices = list(range(start, start + len(pattern)))
        return (1000 + len(pattern), indices)

    # Fuzzy match
    pattern_idx = 0
    text_idx = 0
    matched_indices = []
    score = 0
    consecutive = 0

    while pattern_idx < len(pattern) and text_idx < len(text):
        if pattern[pattern_idx] == text[text_idx]:
            matched_indices.append(text_idx)
            pattern_idx += 1
            consecutive += 1
            score += 1 + consecutive  # Bonus for consecutive matches
        else:
            consecutive = 0
        text_idx += 1

    # All pattern characters must be matched
    if pattern_idx != len(pattern):
        return (0, [])

    # Bonus for matches at word boundaries
    for idx in matched_indices:
        if idx == 0 or text[idx-1] in (' ', '_', '-', '/'):
            score += 5

    return (score, matched_indices)
