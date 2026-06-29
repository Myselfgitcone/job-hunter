import re

# NOTE: the old static ALL_KEYWORDS catalog was removed — score_ats extracts JD
# skills dynamically via resume_lint.skill_coverage_report, so the hardcoded list
# was dead and only misled readers into thinking scoring used it.


def _normalize(text: str) -> str:
    return text.lower()


def score_ats(resume_text: str, job_description: str) -> dict:
    """
    ATS keyword coverage using dynamic JD keyword extraction.
    Delegates to skill_coverage_report() so it stays in sync with
    the tailor pipeline — both use extract_jd_keywords_dynamic()
    instead of a static keyword catalog.
    """
    from resume_lint import skill_coverage_report, find_fragment_bullets
    cov = skill_coverage_report(resume_text, job_description)
    total   = len(cov["jd_skills"])
    matched = cov["covered"]
    missing = cov["missing"]
    score   = round(len(matched) / total * 100) if total else 0
    # Readability surfacing — kept SEPARATE from the score on purpose:
    # blending would let coverage regressions hide behind readability (and
    # vice versa). Score stays pure keyword coverage; fragments are a
    # parallel signal the UI warns about.
    try:
        fragments = find_fragment_bullets(resume_text, context=job_description)
    except Exception:
        fragments = []
    return {
        "score":   score,
        "matched": matched,
        "missing": missing,
        "total":   total,
        "quality": {"fragments": fragments, "count": len(fragments)},
    }
