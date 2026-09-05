from django.db import models


class Developer(models.Model):
    username = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)
    followers = models.PositiveIntegerField(default=0)
    following = models.PositiveIntegerField(default=0)
    public_repos = models.PositiveIntegerField(default=0)
    github_created_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username


class Repository(models.Model):
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name="repositories")
    github_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=200)
    full_name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    primary_language = models.CharField(max_length=100, blank=True)
    # Byte count per language, e.g. {"Python": 50000, "HTML": 5000} — from
    # GraphQL's languages(edges). Richer than primary_language alone: powers
    # the byte-weighted language mix and language-evolution-by-year charts.
    language_bytes = models.JSONField(default=dict, blank=True)
    stars = models.PositiveIntegerField(default=0)
    forks = models.PositiveIntegerField(default=0)
    open_issues = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(null=True, blank=True)
    pushed_at = models.DateTimeField(null=True, blank=True)
    html_url = models.URLField(blank=True)

    def __str__(self):
        return self.full_name


class DailyActivity(models.Model):
    """
    The real historical data layer: one row per developer per day.

    `total` always comes from GitHub's contribution calendar and is exact.
    The commit/PR/issue SPLIT is only exact where GitHub's public Events API
    covers it (roughly the last 90 days) — `source` records which is true
    for that row, rather than silently presenting an estimate as fact.
    """

    SOURCE_CHOICES = [
        ("exact", "Exact (from public events)"),
        ("estimated", "Estimated (proportional from yearly totals)"),
    ]

    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name="daily_activity")
    date = models.DateField()
    commits = models.PositiveIntegerField(default=0)
    pull_requests = models.PositiveIntegerField(default=0)
    issues = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="estimated")

    class Meta:
        unique_together = ("developer", "date")
        indexes = [models.Index(fields=["developer", "date"])]
        ordering = ["date"]

    def __str__(self):
        return f"{self.developer.username} @ {self.date}: {self.total} ({self.source})"


class FollowerSnapshot(models.Model):
    """
    GitHub has no "followers as of date X" endpoint — this is the one metric
    that only gets real history by us recording it ourselves, once per sync.
    """

    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name="follower_snapshots")
    date = models.DateField()
    followers = models.PositiveIntegerField(default=0)
    following = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("developer", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.developer.username} @ {self.date}: {self.followers} followers"
