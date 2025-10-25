from django.http import JsonResponse

from domain.services.database_health import database_health_summary


def database_health(_request):
    """
    Lightweight endpoint that exposes the health of the Singleton database
    connection so SRE dashboards can quickly detect outages.
    """
    summary = database_health_summary()
    status_code = 200 if summary["status"] == "online" else 503
    return JsonResponse(summary, status=status_code)
