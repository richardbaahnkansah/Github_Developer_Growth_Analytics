from datetime import timedelta

from django.utils import timezone

from .models import DailyActivity, Repository
from . import parsing, growth


def period_bounds(days: int):
    end = timezone.now().date()
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    return start, end, previous_start


def dashboard_metrics(developer, days: int = 30) -> dict:
    """
    Matches the original API shape (metrics/previous/changes/days) plus new
    fields (growth_index, recommendations, language breakdowns, repo growth,
    repo health summary) folded into the same response so the frontend needs
    only one call.
    """
    start, end, previous_start = period_bounds(days)

    current_qs = DailyActivity.objects.filter(developer=developer, date__gte=start, date__lte=end)
    previous_qs = DailyActivity.objects.filter(developer=developer, date__gte=previous_start, date__lt=start)

    def agg(qs):
        rows = list(qs)
        return {
            "commits": sum(r.commits for r in rows),
            "pull_requests": sum(r.pull_requests for r in rows),
            "issues": sum(r.issues for r in rows),
            "activities": sum(r.total for r in rows),
            "active_days": sum(1 for r in rows if r.total > 0),
        }

    current = agg(current_qs)
    previous = agg(previous_qs)

    repos = Repository.objects.filter(developer=developer)
    current["repositories"] = repos.count()
    current["stars"] = sum(repos.values_list("stars", flat=True))

    def pct_change(a, b):
        if b == 0:
            return 100.0 if a > 0 else 0.0
        return round(((a - b) / b) * 100, 1)

    changes = {key: pct_change(current[key], previous.get(key, 0)) for key in previous}

    # --- Derived metrics, built on top of the same period's persisted data ---
    repo_dicts = [
        {
            "created_at": r.created_at,
            "language_bytes": r.language_bytes,
            "pushed_at": r.pushed_at,
            "name": r.name,
            "stars": r.stars,
            "primary_language": r.primary_language,
        }
        for r in repos
    ]

    # One shared "top 5 languages" definition, used everywhere a language
    # chart appears, so every chart tells a consistent story.
    top_langs = parsing.top_languages_by_bytes(repo_dicts, n=5)

    all_daily = list(DailyActivity.objects.filter(developer=developer).order_by("date"))
    daily_totals = [r.total for r in all_daily]
    last_30 = DailyActivity.objects.filter(
        developer=developer, date__gte=timezone.now().date() - timedelta(days=30)
    )
    last_30_total = sum(r.total for r in last_30)

    consistency = parsing.compute_consistency(daily_totals, window_days=90)
    language_bytes_breakdown = _language_breakdown_bytes(repo_dicts, top_langs)
    language_count_breakdown = _language_breakdown_by_count(repo_dicts, top_langs)
    repo_health = _repo_health(repo_dicts)
    repo_health_summary = _repo_health_summary(repo_health)

    extra_metrics = {
        "last_30_days_total": last_30_total,
        "consistency": consistency,
        "language_breakdown_bytes": language_bytes_breakdown,
        "year_totals": {
            "commits": sum(r.commits for r in all_daily),
            "pull_requests": sum(r.pull_requests for r in all_daily),
            "issues": sum(r.issues for r in all_daily),
        },
        "repo_health": repo_health,
    }
    growth_index = growth.compute_growth_index(extra_metrics)
    recommendations = growth.generate_recommendations(extra_metrics)

    return {
        "metrics": current,
        "previous": previous,
        "changes": changes,
        "days": days,
        "growth_index": growth_index,
        "recommendations": recommendations,
        "consistency": consistency,
        "language_breakdown_bytes": language_bytes_breakdown,
        "language_breakdown_count": language_count_breakdown,
        "language_evolution": parsing.compute_language_evolution(repo_dicts, top_langs),
        "repo_growth": parsing.compute_repo_growth(repo_dicts),
        "repo_health": repo_health,
        "repo_health_summary": repo_health_summary,
    }


def activity_timeline(developer, days: int = 180) -> list[dict]:
    """Real per-day, per-type activity — exact where Events data covers it, labeled where estimated."""
    start = timezone.now().date() - timedelta(days=days)
    rows = DailyActivity.objects.filter(developer=developer, date__gte=start).order_by("date")
    return [
        {
            "date": str(r.date),
            "commits": r.commits,
            "pull_requests": r.pull_requests,
            "issues": r.issues,
            "source": r.source,
        }
        for r in rows
    ]


def language_breakdown_by_count(developer) -> list[dict]:
    """Standalone endpoint version (kept for the /languages/ route) — no Top-5 grouping, raw counts."""
    repos = Repository.objects.filter(developer=developer).exclude(primary_language="")
    counts = {}
    for lang in repos.values_list("primary_language", flat=True):
        counts[lang] = counts.get(lang, 0) + 1
    return [{"language": lang, "count": c} for lang, c in sorted(counts.items(), key=lambda x: -x[1])]


def _language_breakdown_by_count(repo_dicts: list[dict], top_langs: list[str]) -> list[dict]:
    """Repo count by primary language, grouped to the shared Top-5 + Other set."""
    top_set = set(top_langs)
    counts = {}
    for repo in repo_dicts:
        lang = repo["primary_language"]
        if not lang:
            continue
        key = lang if lang in top_set else "Other"
        counts[key] = counts.get(key, 0) + 1
    return sorted([{"language": k, "count": v} for k, v in counts.items()], key=lambda x: -x["count"])


def _language_breakdown_bytes(repo_dicts: list[dict], top_langs: list[str]) -> list[dict]:
    """Byte-weighted language mix, grouped to the shared Top-5 + Other set."""
    top_set = set(top_langs)
    totals = {}
    for repo in repo_dicts:
        for lang, size in (repo["language_bytes"] or {}).items():
            key = lang if lang in top_set else "Other"
            totals[key] = totals.get(key, 0) + size
    grand_total = sum(totals.values()) or 1
    breakdown = [{"language": lang, "percent": round(size / grand_total * 100, 1)} for lang, size in totals.items()]
    return sorted(breakdown, key=lambda x: -x["percent"])


def _repo_health(repo_dicts: list[dict]) -> list[dict]:
    today = timezone.now().date()
    health = []
    for repo in repo_dicts:
        if not repo["pushed_at"]:
            continue
        days_since = (today - repo["pushed_at"].date()).days
        status = "active" if days_since <= 30 else "maintenance" if days_since <= 180 else "inactive"
        health.append({"name": repo["name"], "stars": repo["stars"], "days_since_push": days_since, "status": status})
    return sorted(health, key=lambda r: r["days_since_push"])


def _repo_health_summary(repo_health: list[dict]) -> dict:
    """Counts by status, plus the 3 most-recently-active and 3 most-stale repos for quick context."""
    counts = {"active": 0, "maintenance": 0, "inactive": 0}
    for r in repo_health:
        counts[r["status"]] += 1
    return {
        "counts": counts,
        "most_active": repo_health[:3],
        "most_stale": sorted(repo_health, key=lambda r: -r["days_since_push"])[:3],
    }
