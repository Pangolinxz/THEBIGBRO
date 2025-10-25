import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from domain.services.database_health import database_health_summary
from domain.services.product_factory_service import (
    build_blueprint_from_payload,
    persist_product_from_blueprint,
)


def database_health(_request):
    """
    Lightweight endpoint that exposes the health of the Singleton database
    connection so SRE dashboards can quickly detect outages.
    """
    summary = database_health_summary()
    status_code = 200 if summary["status"] == "online" else 503
    return JsonResponse(summary, status=status_code)


@csrf_exempt
@require_http_methods(["POST"])
def product_factory(request):
    """
    Exposes the Factory Method so UX teams can preview how un nuevo producto
    seria registrado y, opcionalmente, persistido en la base de datos.
    """
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    try:
        blueprint = build_blueprint_from_payload(payload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    response_data = blueprint.summary()
    if request.GET.get("persist") == "true":
        product = persist_product_from_blueprint(blueprint)
        response_data["product_id"] = product.id
        return JsonResponse(response_data, status=201)

    return JsonResponse(response_data, status=200)
