"""
Developer Growth Index and recommendation engine.

Both are pure functions taking the metrics dict analytics.py assembles from
the database — no ORM dependency, so both are unit-testable in isolation.
Each sub-score's formula is documented inline rather than hidden behind a
model; adjust the baselines as real usage shows what "good" looks like.
"""


def _activity_score(metrics: dict) -> int:
    """Baseline: ~2 contributions/day over the last 30 days (60 total) = 100."""
    return min(100, round(metrics["last_30_days_total"] / 60 * 100))


def _consistency_score(metrics: dict) -> int:
    return metrics["consistency"]["score"]


def _technical_growth_score(metrics: dict) -> int:
    """Baseline: familiarity with 5+ languages = fully diversified = 100."""
    return min(100, len(metrics["language_breakdown_bytes"]) * 20)


def _collaboration_score(metrics: dict) -> int:
    """Baseline: a PR+issue-to-commit ratio of 0.2 = strong collaboration = 100."""
    commits = metrics["year_totals"]["commits"]
    collab = metrics["year_totals"]["pull_requests"] + metrics["year_totals"]["issues"]
    ratio = collab / (commits + 1)
    return min(100, round(ratio * 500))


def _project_development_score(metrics: dict) -> int:
    """Share of repos pushed to within the last 6 months."""
    repos = metrics["repo_health"]
    if not repos:
        return 0
    healthy = sum(1 for r in repos if r["status"] in ("active", "maintenance"))
    return round(healthy / len(repos) * 100)


def compute_growth_index(metrics: dict) -> dict:
    sub_scores = {
        "activity": _activity_score(metrics),
        "consistency": _consistency_score(metrics),
        "technical_growth": _technical_growth_score(metrics),
        "collaboration": _collaboration_score(metrics),
        "project_development": _project_development_score(metrics),
    }
    overall = round(sum(sub_scores.values()) / len(sub_scores))
    return {"overall": overall, "sub_scores": sub_scores}


def generate_recommendations(metrics: dict) -> list[dict]:
    recs = []

    consistency = metrics["consistency"]["score"]
    if consistency < 40:
        recs.append(
            {
                "title": "Build a more consistent commit habit",
                "detail": (
                    f"You've been active on {metrics['consistency']['active_days']} of the last "
                    f"{metrics['consistency']['window_days']} days. Frequent small commits build a "
                    "stronger habit than occasional large ones."
                ),
                "severity": "high",
            }
        )
    elif consistency >= 70:
        recs.append(
            {
                "title": "Strong consistency — keep it up",
                "detail": f"You're active on {consistency}% of recent days. That's a solid habit.",
                "severity": "positive",
            }
        )

    languages = metrics["language_breakdown_bytes"]
    if languages and languages[0]["percent"] > 80:
        recs.append(
            {
                "title": "Language profile is heavily concentrated",
                "detail": (
                    f"{languages[0]['language']} makes up {languages[0]['percent']}% of your code. "
                    "A side project in a second language can broaden what you're able to work on."
                ),
                "severity": "low",
            }
        )

    repos = metrics["repo_health"]
    inactive = [r for r in repos if r["status"] == "inactive"]
    if repos and len(inactive) / len(repos) > 0.5:
        recs.append(
            {
                "title": "Most repositories are inactive",
                "detail": (
                    f"{len(inactive)} of {len(repos)} repos haven't been pushed to in 6+ months. "
                    "Consider archiving abandoned ones so your active profile is easier to read."
                ),
                "severity": "low",
            }
        )

    commits = metrics["year_totals"]["commits"]
    collab = metrics["year_totals"]["pull_requests"] + metrics["year_totals"]["issues"]
    if commits > 50 and collab / (commits + 1) < 0.02:
        recs.append(
            {
                "title": "Low collaboration signal",
                "detail": (
                    "You commit regularly but rarely open pull requests or issues. Contributing to "
                    "other projects, even in small ways, is a strong collaboration signal."
                ),
                "severity": "low",
            }
        )

    if not recs:
        recs.append(
            {
                "title": "Well-rounded profile",
                "detail": "No major gaps detected across activity, consistency, or collaboration.",
                "severity": "positive",
            }
        )

    return recs
