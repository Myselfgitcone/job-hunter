# -*- coding: utf-8 -*-
import re


def lint_resume(text: str) -> list:
    """
    Check a tailored resume for detectable quality issues.
    Returns a list of human-readable issue strings (empty list = clean).
    """
    issues = []
    bullets = [l.strip() for l in text.split("\n") if l.strip().startswith("•")]

    # 1. Bullets over 22 words
    long_bullets = []
    for b in bullets:
        word_count = len(b.split()) - 1  # subtract bullet char
        if word_count > 22:
            preview = " ".join(b.split()[1:9]) + "..."
            long_bullets.append(f'  • "{preview}" ({word_count} words)')
    if long_bullets:
        issues.append(
            f"BULLET LENGTH: {len(long_bullets)} bullet(s) exceed 22 words. "
            "Shorten to 14–18 words — one idea per bullet. Split bullets joined by 'and' or an em-dash:\n"
            + "\n".join(long_bullets)
        )

    # 2. Banned words
    found_banned = []
    for b in bullets:
        for word in ("utilized", "leveraged"):
            if re.search(r"\b" + word + r"\b", b, re.IGNORECASE):
                found_banned.append(f'  • contains "{word}": {b[:70]}')
    if found_banned:
        issues.append(
            "BANNED WORDS: Replace 'utilized'→'used', 'leveraged'→'used'/'built'/'applied':\n"
            + "\n".join(found_banned)
        )

    # 3. Consecutive bullets opening with the same verb
    for i in range(1, len(bullets)):
        words_prev = bullets[i - 1].lstrip("• ").split()
        words_curr = bullets[i].lstrip("• ").split()
        if not words_prev or not words_curr:
            continue
        v1 = words_prev[0].lower().rstrip(",")
        v2 = words_curr[0].lower().rstrip(",")
        if v1 == v2 and len(v1) > 3:
            issues.append(
                f"REPEATED OPENER: Two consecutive bullets both start with '{v1.capitalize()}'. "
                "Change one opener to a different action verb."
            )

    # 4. Vague intensifiers without a number
    intensifiers = ["significantly", "substantially", "dramatically", "greatly", "considerably"]
    for b in bullets:
        b_lower = b.lower()
        for word in intensifiers:
            if word in b_lower and not re.search(r"\d", b):
                issues.append(
                    f"VAGUE INTENSIFIER: '{word}' used without a supporting number in: {b[:80]}"
                )
                break

    return issues
