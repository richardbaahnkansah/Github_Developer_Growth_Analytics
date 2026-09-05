"""
Pure functions only — no Django ORM here. Everything takes plain
dicts/lists in and returns plain dicts/lists out, which means it's fully
unit-testable without a database or network access. `ingestion.py` and
`analytics.py` are the thin Django-dependent layers that call into this.
"""

from collections import defaultdict
from datetime import date as date_cls
from datetime import datetime, timedelta


def _parse_date(s: str) -> date_cls:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


# ---------- GraphQL response parsing ----------

def parse_graphql_user(user_data: dict) -> dict:
    """Normalize the raw GraphQL `user` object into the pieces ingestion.py needs."""
    cc = user_data["contributionsCollection"]
    calendar_days = []
    for week in cc["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            calendar_days.append({"date": day["date"], "count": day["contributionCount"]})

    return {
        "profile": {
            "login": user_data["login"],
            "name": user_data.get("name") or "",
            "bio": user_data.get("bio") or "",
            "avatar_url": user_data.get("avatarUrl") or "",
            "followers": user_data["followers"]["totalCount"],
            "following": user_data["following"]["totalCount"],
            "public_repos": user_data["repositories"]["totalCount"],
            "created_at": user_data.get("createdAt"),
        },
        "repos": user_data["repositories"]["nodes"],
        "calendar_days": calendar_days,
        "year_totals": {
            "commits": cc["totalCommitContributions"],
            "pull_requests": cc["totalPullRequestContributions"],
            "issues": cc["totalIssueContributions"],
            "total": cc["contributionCalendar"]["totalContributions"],
        },
    }


# ---------- Events API parsing (exact recent type-breakdown) ----------

EVENT_TYPE_MAP = {
    "PushEvent": "commits",
    "PullRequestEvent": "pull_requests",
    "IssuesEvent": "issues",
    "IssueCommentEvent": "issues",
}


def bucket_events_by_day(events: list[dict]) -> dict[str, dict]:
    """
    GitHub's public Events API gives exact, dated events but only covers
    roughly the last 90 days / 300 events. Bucket them into per-day
    per-type counts wherever this data is available.
    """
    buckets = defaultdict(lambda: {"commits": 0, "pull_requests": 0, "issues": 0})
    for event in events:
        field = EVENT_TYPE_MAP.get(event.get("type"))
        if not field:
            continue
        created = event.get("created_at")
        if not created:
            continue
        day = created[:10]  # "2026-01-15T10:00:00Z" -> "2026-01-15"
        if field == "commits":
            # A single PushEvent can bundle multiple commits.
            buckets[day][field] += len(event.get("payload", {}).get("commits", []) or []) or 1
        else:
            buckets[day][field] += 1
    return dict(buckets)


# ---------- Merge into the real historical layer ----------

def merge_daily_activity(calendar_days: list[dict], year_totals: dict, events_by_day: dict) -> list[dict]:
    """
    For each day in the full-year calendar: the combined `total` is always
    exact (straight from GitHub's calendar). The commit/PR/issue SPLIT is
    exact wherever the Events API covers that day; otherwise it's estimated
    by applying the year's overall commit:PR:issue ratio to that day's total.
    Each row is honestly labeled with which is true.
    """
    year_total = year_totals["total"] or 1
    commit_ratio = year_totals["commits"] / year_total
    pr_ratio = year_totals["pull_requests"] / year_total
    issue_ratio = year_totals["issues"] / year_total

    rows = []
    for day in calendar_days:
        total = day["count"]
        if day["date"] in events_by_day:
            ev = events_by_day[day["date"]]
            rows.append(
                {
                    "date": day["date"],
                    "commits": ev["commits"],
                    "pull_requests": ev["pull_requests"],
                    "issues": ev["issues"],
                    "total": total,
                    "source": "exact",
                }
            )
        else:
            rows.append(
                {
                    "date": day["date"],
                    "commits": round(total * commit_ratio),
                    "pull_requests": round(total * pr_ratio),
                    "issues": round(total * issue_ratio),
                    "total": total,
                    "source": "estimated",
                }
            )
    return rows


# ---------- Derived metrics (all operate on already-fetched repo/activity data) ----------

def compute_repo_growth(repos: list[dict]) -> list[dict]:
    """Cumulative repo count over time, from each repo's creation date."""
    sorted_repos = sorted(repos, key=lambda r: r["created_at"] if isinstance(r["created_at"], str) else r["created_at"].isoformat())
    return [
        {"date": str(r["created_at"])[:10], "cumulative_repos": i}
        for i, r in enumerate(sorted_repos, start=1)
    ]


def top_languages_by_bytes(repos: list[dict], n: int = 5) -> list[str]:
    """
    The single source of truth for which languages count as a developer's
    main languages, ranked by total code volume in bytes rather than repo
    count, since one large repo says more about skill depth than many tiny
    ones. Used to keep the technical-breadth chart and the language-
    evolution chart showing the same top languages, with everything else
    folded into one consistent Other bucket, rather than each chart
    picking its own cutoff and producing a confusing, differing set of
    categories.
    """
    totals = defaultdict(int)
    for repo in repos:
        for lang, size in (repo.get("language_bytes") or {}).items():
            totals[lang] += size
    ranked = sorted(totals.items(), key=lambda x: -x[1])
    return [lang for lang, _ in ranked[:n]]


def compute_language_evolution(repos: list[dict], top_languages: list[str] | None = None) -> list[dict]:
    """
    Approximates language usage over time by grouping each repo's language
    bytes under the year it was created. GitHub doesn't cheaply expose
    per-commit language history, so this is a proxy — which languages you
    were starting new projects in, year over year — not a literal commit-
    level trend.

    Languages outside `top_languages` are folded into "Other" so the chart
    stays readable regardless of how many distinct languages appear across
    a developer's repos. Each "Other" row carries a `breakdown` field
    listing exactly which languages were folded in and their individual
    share of that year, so hovering over "Other" isn't a dead end.
    """
    top_set = set(top_languages) if top_languages is not None else None

    by_year = defaultdict(lambda: defaultdict(int))
    other_detail = defaultdict(lambda: defaultdict(int))
    for repo in repos:
        created = repo["created_at"]
        year = created.year if hasattr(created, "year") else _parse_date(created).year
        for lang, size in (repo.get("language_bytes") or {}).items():
            if top_set is None or lang in top_set:
                by_year[year][lang] += size
            else:
                by_year[year]["Other"] += size
                other_detail[year][lang] += size

    result = []
    for year in sorted(by_year.keys()):
        year_total = sum(by_year[year].values()) or 1
        for lang, size in by_year[year].items():
            row = {"year": year, "language": lang, "percent": round(size / year_total * 100, 1)}
            if lang == "Other" and other_detail[year]:
                row["breakdown"] = sorted(
                    [
                        {"language": l, "percent": round(s / year_total * 100, 1)}
                        for l, s in other_detail[year].items()
                    ],
                    key=lambda x: -x["percent"],
                )
            result.append(row)
    return result


def language_breakdown_by_count(repos: list[dict], top_languages: list[str]) -> list[dict]:
    """
    Repo count by primary language, grouped to the shared Top-N + Other
    set. Pure function (no ORM) so it's testable in isolation — analytics.py
    just feeds it plain dicts pulled from the database.
    """
    top_set = set(top_languages)
    counts = {}
    other_detail = {}
    for repo in repos:
        lang = repo.get("primary_language")
        if not lang:
            continue
        if lang in top_set:
            counts[lang] = counts.get(lang, 0) + 1
        else:
            counts["Other"] = counts.get("Other", 0) + 1
            other_detail[lang] = other_detail.get(lang, 0) + 1

    result = sorted([{"language": k, "count": v} for k, v in counts.items()], key=lambda x: -x["count"])
    for row in result:
        if row["language"] == "Other" and other_detail:
            row["breakdown"] = sorted(
                [{"language": l, "count": c} for l, c in other_detail.items()], key=lambda x: -x["count"]
            )
    return result


def language_breakdown_by_bytes(repos: list[dict], top_languages: list[str]) -> list[dict]:
    """Byte-weighted language mix, grouped to the shared Top-N + Other set, with an Other breakdown."""
    top_set = set(top_languages)
    totals = {}
    other_detail = {}
    for repo in repos:
        for lang, size in (repo.get("language_bytes") or {}).items():
            if lang in top_set:
                totals[lang] = totals.get(lang, 0) + size
            else:
                totals["Other"] = totals.get("Other", 0) + size
                other_detail[lang] = other_detail.get(lang, 0) + size

    grand_total = sum(totals.values()) or 1
    result = sorted(
        [{"language": lang, "percent": round(size / grand_total * 100, 1)} for lang, size in totals.items()],
        key=lambda x: -x["percent"],
    )
    for row in result:
        if row["language"] == "Other" and other_detail:
            row["breakdown"] = sorted(
                [{"language": l, "percent": round(s / grand_total * 100, 1)} for l, s in other_detail.items()],
                key=lambda x: -x["percent"],
            )
    return result


def compute_consistency(daily_totals: list[int], window_days: int = 90) -> dict:
    """
    Consistency = active-day ratio over the trailing window, plus current
    streak. `daily_totals` should be ordered oldest-to-newest, one entry per
    day in the window (0 for inactive days).
    """
    recent = daily_totals[-window_days:]
    active_days = sum(1 for t in recent if t > 0)
    score = round((active_days / len(recent)) * 100) if recent else 0

    streak = 0
    for t in reversed(daily_totals):
        if t > 0:
            streak += 1
        else:
            break

    return {"score": score, "active_days": active_days, "window_days": len(recent), "current_streak_days": streak}
