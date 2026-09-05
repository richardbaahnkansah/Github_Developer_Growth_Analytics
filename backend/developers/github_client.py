"""
Two data sources, combined deliberately:

- GraphQL `contributionsCollection` gives a full 12-month daily calendar
  plus profile/repo data — but only combined daily totals, no commit/PR/
  issue split per day.
- The REST public Events API gives an exact, dated, per-type breakdown —
  but GitHub caps it at roughly the last 90 days / 300 events.

parsing.merge_daily_activity() combines both: exact type-splits where
Events covers a day, honestly-labeled estimates (from the year's overall
ratio) everywhere older.

Repositories are fetched via full cursor pagination (see fetch_graphql_data),
ordered by creation date — NOT capped at the first page ordered by recency.
An earlier version capped at the first 100 repos ordered by most-recently-
updated, which silently dropped old, dormant repos beyond that page and
corrupted the repository-growth chart for any account with 100+ repos.

`ownerAffiliations: [OWNER]` is set explicitly. GitHub's GraphQL API
defaults this to [OWNER, COLLABORATOR] when unset — meaning an earlier
version of this query was silently including repos this person merely
collaborates on (someone else's repo, someone else's creation date),
inflating repo counts and corrupting the growth chart, language breakdown,
and repo health for anyone who collaborates on repos they don't own.
"""

import requests
from django.conf import settings

GRAPHQL_URL = "https://api.github.com/graphql"
REST_BASE_URL = "https://api.github.com"

MAX_REPO_PAGES = 5  # 5 x 100 = 500 repos, a generous safety cap

REPO_FIELDS = """
databaseId
name
nameWithOwner
description
url
createdAt
pushedAt
stargazerCount
forkCount
issues(states: OPEN) { totalCount }
primaryLanguage { name }
languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
  edges { size node { name } }
}
"""

# First page: profile + contributionsCollection + first page of repos.
# Ordered by CREATED_AT ascending (not UPDATED_AT) so that if pagination
# ever needs to stop early for an unusually large account, what's captured
# is still a correct, uninterrupted history from the beginning.
GRAPHQL_QUERY = f"""
query($login: String!) {{
  user(login: $login) {{
    login
    name
    bio
    avatarUrl
    createdAt
    followers {{ totalCount }}
    following {{ totalCount }}
    repositories(first: 100, ownerAffiliations: [OWNER], isFork: false, orderBy: {{field: CREATED_AT, direction: ASC}}) {{
      totalCount
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ {REPO_FIELDS} }}
    }}
    contributionsCollection {{
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {{
        totalContributions
        weeks {{ contributionDays {{ date contributionCount }} }}
      }}
    }}
  }}
}}
"""

# Subsequent pages: repositories only, using the cursor from the previous page.
REPO_PAGE_QUERY = f"""
query($login: String!, $after: String!) {{
  user(login: $login) {{
    repositories(first: 100, ownerAffiliations: [OWNER], isFork: false, after: $after, orderBy: {{field: CREATED_AT, direction: ASC}}) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ {REPO_FIELDS} }}
    }}
  }}
}}
"""


class GitHubAPIError(Exception):
    pass


class GitHubUserNotFound(GitHubAPIError):
    pass


class GitHubClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if settings.GITHUB_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    def _graphql(self, query: str, variables: dict) -> dict:
        resp = self.session.post(GRAPHQL_URL, json={"query": query, "variables": variables}, timeout=15)
        if resp.status_code != 200:
            raise GitHubAPIError(f"GitHub GraphQL API returned {resp.status_code}: {resp.text}")

        payload = resp.json()
        if "errors" in payload:
            messages = [e.get("message", "") for e in payload["errors"]]
            if any("Could not resolve to a User" in m for m in messages):
                raise GitHubUserNotFound(f"No GitHub user found")
            raise GitHubAPIError(str(payload["errors"]))

        user = payload.get("data", {}).get("user")
        if user is None:
            raise GitHubUserNotFound("No GitHub user found")
        return user

    def fetch_graphql_data(self, username: str) -> dict:
        """
        Returns the `user` object with `repositories.nodes` containing ALL
        of the user's public, non-fork repos (paginated, up to
        MAX_REPO_PAGES x 100), not just the first page.
        """
        user = self._graphql(GRAPHQL_QUERY, {"login": username})

        repos_conn = user["repositories"]
        all_nodes = list(repos_conn["nodes"])
        page_info = repos_conn["pageInfo"]
        pages_fetched = 1

        while page_info["hasNextPage"] and pages_fetched < MAX_REPO_PAGES:
            page_user = self._graphql(REPO_PAGE_QUERY, {"login": username, "after": page_info["endCursor"]})
            page_repos = page_user["repositories"]
            all_nodes.extend(page_repos["nodes"])
            page_info = page_repos["pageInfo"]
            pages_fetched += 1

        user["repositories"]["nodes"] = all_nodes
        return user

    def fetch_public_events(self, username: str, max_pages: int = 3) -> list[dict]:
        """
        Up to 3 pages (300 events) — GitHub's own ceiling for this endpoint
        regardless of how much is requested, so this is the practical max.
        """
        events = []
        for page in range(1, max_pages + 1):
            resp = self.session.get(
                f"{REST_BASE_URL}/users/{username}/events/public",
                params={"per_page": 100, "page": page},
                timeout=15,
            )
            if resp.status_code != 200:
                break  # Events are a nice-to-have; don't fail the whole sync over this.
            batch = resp.json()
            if not batch:
                break
            events.extend(batch)
        return events
