from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle

from .models import Developer
from .serializers import DeveloperSerializer, RepositorySerializer
from .ingestion import sync_developer
from .github_client import GitHubUserNotFound, GitHubAPIError
from .analytics import dashboard_metrics, activity_timeline, language_breakdown_by_count


class SyncRateThrottle(AnonRateThrottle):
    """
    /sync/ makes real GitHub API calls (GraphQL + up to 3 Events pages) and
    is shared across every visitor via one server-side token — throttled
    harder than plain reads.
    """
    scope = "sync"


@api_view(["GET"])
def developer_detail(request, username):
    developer = Developer.objects.filter(username__iexact=username).first()
    if not developer:
        return Response({"detail": "Developer not found. Run sync first."}, status=status.HTTP_404_NOT_FOUND)
    return Response(DeveloperSerializer(developer).data)


@api_view(["GET"])
def repositories(request, username):
    developer = Developer.objects.filter(username__iexact=username).first()
    if not developer:
        return Response({"detail": "Developer not found."}, status=404)
    repos = developer.repositories.all().order_by("-stars", "-pushed_at")
    return Response(RepositorySerializer(repos, many=True).data)


@api_view(["POST"])
@throttle_classes([SyncRateThrottle])
def sync(request, username):
    try:
        developer = sync_developer(username)
        return Response({
            "message": f"Synced {username}",
            "developer": DeveloperSerializer(developer).data,
            "repositories": developer.repositories.count(),
        })
    except GitHubUserNotFound as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except GitHubAPIError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(["GET"])
def dashboard(request, username):
    developer = Developer.objects.filter(username__iexact=username).first()
    if not developer:
        return Response({"detail": "Developer not found. Run sync first."}, status=404)
    days = int(request.GET.get("days", 30))
    days = max(7, min(days, 365))  # capped at 365: that's the real coverage a single sync provides
    data = dashboard_metrics(developer, days)
    data["developer"] = DeveloperSerializer(developer).data
    return Response(data)


@api_view(["GET"])
def timeline(request, username):
    developer = Developer.objects.filter(username__iexact=username).first()
    if not developer:
        return Response({"detail": "Developer not found. Run sync first."}, status=404)
    days = int(request.GET.get("days", 180))
    days = max(7, min(days, 365))
    return Response(activity_timeline(developer, days))


@api_view(["GET"])
def languages(request, username):
    developer = Developer.objects.filter(username__iexact=username).first()
    if not developer:
        return Response({"detail": "Developer not found. Run sync first."}, status=404)
    return Response(language_breakdown_by_count(developer))
