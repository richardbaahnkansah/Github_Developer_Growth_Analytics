from django.utils.dateparse import parse_datetime
from django.utils import timezone

from .models import Developer, Repository, DailyActivity, FollowerSnapshot
from .github_client import GitHubClient
from . import parsing


def _parse_dt(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def sync_developer(username: str) -> Developer:
    """
    The one "expensive" action in this app — makes real GitHub API calls
    and persists everything. Everything else (dashboard, timeline, etc.)
    reads from the database afterwards, no further GitHub calls needed
    until the next sync.
    """
    client = GitHubClient()
    user_data = client.fetch_graphql_data(username)
    events = client.fetch_public_events(username)

    parsed = parsing.parse_graphql_user(user_data)
    profile = parsed["profile"]

    # GitHub usernames are case-insensitive, but stored with their real
    # ("canonical") case. Match any existing row case-insensitively first,
    # so re-syncing "Torvalds" after "torvalds" updates the same developer
    # instead of creating a duplicate.
    developer = Developer.objects.filter(username__iexact=profile["login"]).first()
    if developer is None:
        developer = Developer(username=profile["login"])

    developer.username = profile["login"]  # always normalize to GitHub's canonical case
    developer.name = profile["name"]
    developer.bio = profile["bio"]
    developer.avatar_url = profile["avatar_url"]
    developer.followers = profile["followers"]
    developer.following = profile["following"]
    developer.public_repos = profile["public_repos"]
    developer.github_created_at = _parse_dt(profile["created_at"])
    developer.save()

    for repo in parsed["repos"]:
        language_bytes = {
            edge["node"]["name"]: edge["size"] for edge in repo["languages"]["edges"]
        }
        Repository.objects.update_or_create(
            github_id=repo["databaseId"],
            defaults={
                "developer": developer,
                "name": repo["name"],
                "full_name": repo["nameWithOwner"],
                "description": repo.get("description") or "",
                "primary_language": (repo.get("primaryLanguage") or {}).get("name", ""),
                "language_bytes": language_bytes,
                "stars": repo["stargazerCount"],
                "forks": repo["forkCount"],
                "open_issues": repo["issues"]["totalCount"],
                "created_at": _parse_dt(repo["createdAt"]),
                "pushed_at": _parse_dt(repo["pushedAt"]),
                "html_url": repo.get("url") or "",
            },
        )

    events_by_day = parsing.bucket_events_by_day(events)
    daily_rows = parsing.merge_daily_activity(parsed["calendar_days"], parsed["year_totals"], events_by_day)
    for row in daily_rows:
        DailyActivity.objects.update_or_create(
            developer=developer,
            date=row["date"],
            defaults={
                "commits": row["commits"],
                "pull_requests": row["pull_requests"],
                "issues": row["issues"],
                "total": row["total"],
                "source": row["source"],
            },
        )

    FollowerSnapshot.objects.update_or_create(
        developer=developer,
        date=timezone.now().date(),
        defaults={"followers": profile["followers"], "following": profile["following"]},
    )

    return developer
