import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

from django.http import JsonResponse
from django.db.models.deletion import ProtectedError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout

from core.models import (
    Inventory,
    InventoryAudit,
    InventoryTransaction,
    Location,
    Order,
    OrderItem,
    Product,
    Rol,
    StockAlert,
    StockAdjustmentRequest,
    InternalTransfer,
    TransferStatus,
    User,
)
from domain.services.adjustments import (
    AdjustmentRequestError,
    approve_adjustment,
    create_adjustment_request,
    get_adjustment_request,
    list_adjustment_requests,
    reject_adjustment,
)
from domain.services.transfers import (
    TransferRequestError,
    approve_transfer,
    reject_transfer,
    get_internal_transfer,
    list_internal_transfers,
)
from domain.services.database_health import database_health_summary
from domain.services.product_factory_service import (
    build_blueprint_from_payload,
    persist_product_from_blueprint,
)
from domain.services.inventory_ingress import (
    IngressError,
    list_ingress_records,
    register_product_ingress,
)

MODEL_REGISTRY = {
    "roles": Rol,
    "users": User,
    "products": Product,
    "locations": Location,
    "inventories": Inventory,
    "inventory-transactions": InventoryTransaction,
    "inventory-audits": InventoryAudit,
    "orders": Order,
    "order-items": OrderItem,
    "stock-alerts": StockAlert,
    "internal-transfers": InternalTransfer,
}


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


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _serialize_instance(instance) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        if field.auto_created:
            continue
        if field.is_relation and field.many_to_one:
            raw_value = getattr(instance, field.attname)
            related = getattr(instance, field.name)
            data[field.name] = raw_value
            data[f"{field.name}_display"] = str(related) if related else None
        else:
            data[field.name] = _serialize_value(getattr(instance, field.name))
    data["id"] = getattr(instance, "id", None)
    return data


def _clean_payload(model, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    cleaned: Dict[str, Any] = {}
    for field in model._meta.concrete_fields:
        if field.auto_created or field.primary_key:
            continue
        key = field.attname if field.is_relation and field.many_to_one else field.name
        if key in payload:
            raw_value = payload[key]
            try:
                cleaned[key] = field.get_prep_value(raw_value)
            except Exception as exc:  # pragma: no cover - defensive
                return {}, f"Valor invalido para {key}: {exc}"
    return cleaned, None


def _serialize_adjustment_request(instance: StockAdjustmentRequest) -> Dict[str, Any]:
    return {
        "id": instance.id,
        "product_id": instance.product_id,
        "product_sku": instance.product.sku,
        "product_name": instance.product.name,
        "location_id": instance.location_id,
        "location_code": instance.location.code,
        "system_quantity": instance.system_quantity,
        "physical_quantity": instance.physical_quantity,
        "delta": instance.delta,
        "flagged": instance.flagged,
        "status": instance.status,
        "reason": instance.reason,
        "attachment_url": instance.attachment_url or None,
        "created_by": instance.created_by.username if instance.created_by else None,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "processed_by": instance.processed_by.username if instance.processed_by else None,
        "processed_at": instance.processed_at.isoformat() if instance.processed_at else None,
        "resolution_comment": instance.resolution_comment or None,
    }


def _serialize_inventory_audit(instance: InventoryAudit) -> Dict[str, Any]:
    return {
        "id": instance.id,
        "product_id": instance.product_id,
        "product_sku": instance.product.sku,
        "product_name": instance.product.name,
        "location_id": instance.location_id,
        "location_code": instance.location.code,
        "user": instance.user.username if instance.user else None,
        "movement_type": instance.movement_type,
        "quantity": instance.quantity,
        "previous_stock": instance.previous_stock,
        "new_stock": instance.new_stock,
        "observations": instance.observations or None,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
    }


def _serialize_internal_transfer(instance: InternalTransfer) -> Dict[str, Any]:
    return {
        "id": instance.id,
        "product_id": instance.product_id,
        "product_sku": instance.product.sku,
        "quantity": instance.quantity,
        "origin_location_id": instance.origin_location_id,
        "origin_location_code": instance.origin_location.code,
        "destination_location_id": instance.destination_location_id,
        "destination_location_code": instance.destination_location.code,
        "reason": instance.reason,
        "status": instance.status,
        "created_by": instance.created_by.username if instance.created_by else None,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "processed_by": instance.processed_by.username if instance.processed_by else None,
        "processed_at": instance.processed_at.isoformat() if instance.processed_at else None,
        "resolution_comment": instance.resolution_comment or None,
    }


def _get_model(model_key: str):
    model = MODEL_REGISTRY.get(model_key)
    if not model:
        return None, JsonResponse({"error": f"Modelo '{model_key}' no soportado"}, status=404)
    return model, None


@csrf_exempt
def crud_collection(request, model_key: str):
    model, error_response = _get_model(model_key)
    if error_response:
        return error_response

    if request.method == "GET":
        items = [_serialize_instance(instance) for instance in model.objects.all().order_by("id")]
        return JsonResponse({"items": items, "count": len(items)}, status=200)

    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invalido"}, status=400)

        cleaned, error = _clean_payload(model, payload)
        if error:
            return JsonResponse({"error": error}, status=400)
        try:
            instance = model.objects.create(**cleaned)
        except Exception as exc:  # pragma: no cover - depende del driver
            return JsonResponse({"error": f"No se pudo crear el registro: {exc}"}, status=400)
        return JsonResponse(_serialize_instance(instance), status=201)

    return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)


@csrf_exempt
def crud_resource(request, model_key: str, pk: int):
    model, error_response = _get_model(model_key)
    if error_response:
        return error_response

    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({"error": f"Registro {pk} no encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_instance(instance), status=200)

    if request.method in {"PUT", "PATCH"}:
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invalido"}, status=400)

        cleaned, error = _clean_payload(model, payload)
        if error:
            return JsonResponse({"error": error}, status=400)

        for key, value in cleaned.items():
            setattr(instance, key, value)
        try:
            instance.save()
        except Exception as exc:  # pragma: no cover - depende del driver
            return JsonResponse({"error": f"No se pudo actualizar el registro: {exc}"}, status=400)
        return JsonResponse(_serialize_instance(instance), status=200)

    if request.method == "DELETE":
        try:
            instance.delete()
        except ProtectedError as exc:
            references = [str(obj) for obj in exc.protected_objects]
            return JsonResponse(
                {
                    "error": "No se puede eliminar porque existen referencias protegidas.",
                    "references": references,
                },
                status=409,
            )
    return JsonResponse({}, status=204)

    return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)


@csrf_exempt
def inventory_ingress(request):
    if request.method == "GET":
        limit_param = request.GET.get("limit")
        limit = 50
        if limit_param:
            try:
                limit = max(int(limit_param), 1)
            except ValueError:
                return JsonResponse({"error": "El parametro limit debe ser entero positivo"}, status=400)
        audits = list_ingress_records(limit=limit)
        items = [_serialize_inventory_audit(audit) for audit in audits]
        return JsonResponse({"items": items, "count": len(items)}, status=200)

    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invalido"}, status=400)

        try:
            result = register_product_ingress(payload, created_by=None)  # TODO auth
        except IngressError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        response_payload = {
            "audit": _serialize_inventory_audit(result.audit),
            "inventory": {
                "product_id": result.inventory.product_id,
                "location_id": result.inventory.location_id,
                "quantity": result.inventory.quantity,
                "updated_at": result.inventory.updated_at.isoformat()
                if result.inventory.updated_at
                else None,
            },
            "transaction": {
                "id": result.transaction.id,
                "type": result.transaction.type,
                "quantity": result.transaction.quantity,
                "created_at": result.transaction.created_at.isoformat()
                if result.transaction.created_at
                else None,
            },
        }
        return JsonResponse(response_payload, status=201)

    return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)


@csrf_exempt
def adjustment_requests(request):
    if request.method == "GET":
        queryset = list_adjustment_requests(request.GET)
        items = [_serialize_adjustment_request(instance) for instance in queryset]
        return JsonResponse({"items": items, "count": len(items)}, status=200)

    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invalido"}, status=400)

        try:
            adjustment = create_adjustment_request(payload, created_by=None)  # TODO auth
        except AdjustmentRequestError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        return JsonResponse(_serialize_adjustment_request(adjustment), status=201)

    return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)


@csrf_exempt
def adjustment_request_detail(request, pk: int):
    try:
        adjustment = get_adjustment_request(pk)
    except StockAdjustmentRequest.DoesNotExist:
        return JsonResponse({"error": f"Solicitud {pk} no encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_adjustment_request(adjustment), status=200)

    return JsonResponse({"error": "Operacion no implementada. TODO auth/approval"}, status=405)


@csrf_exempt
@require_http_methods(["PATCH"])
def adjustment_approve(request, pk: int):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    comment = str(payload.get("comment") or "").strip()
    try:
        adjustment = approve_adjustment(pk, supervisor_user=None, comment=comment)  # TODO auth
    except StockAdjustmentRequest.DoesNotExist:
        return JsonResponse({"error": f"Solicitud {pk} no encontrada"}, status=404)
    except AdjustmentRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize_adjustment_request(adjustment), status=200)


@csrf_exempt
@require_http_methods(["PATCH"])
def adjustment_reject(request, pk: int):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    comment = str(payload.get("comment") or "").strip()
    if not comment:
        return JsonResponse({"error": "Debe proporcionar un comentario para rechazar"}, status=400)

    try:
        adjustment = reject_adjustment(pk, supervisor_user=None, comment=comment)  # TODO auth
    except StockAdjustmentRequest.DoesNotExist:
        return JsonResponse({"error": f"Solicitud {pk} no encontrada"}, status=404)
    except AdjustmentRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize_adjustment_request(adjustment), status=200)


@csrf_exempt
def internal_transfers_pending(request):
    if request.method != "GET":
        return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)
    queryset = list_internal_transfers({"status": TransferStatus.PENDING})
    items = [_serialize_internal_transfer(instance) for instance in queryset]
    return JsonResponse({"items": items, "count": len(items)}, status=200)


@csrf_exempt
def internal_transfer_detail(request, pk: int):
    try:
        transfer = get_internal_transfer(pk)
    except InternalTransfer.DoesNotExist:
        return JsonResponse({"error": f"Transferencia {pk} no encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_internal_transfer(transfer), status=200)

    return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)


@csrf_exempt
@require_http_methods(["PATCH"])
def internal_transfer_approve(request, pk: int):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    comment = str(payload.get("comment") or "").strip()
    try:
        transfer = approve_transfer(pk, supervisor_user=None, comment=comment)  # TODO auth
    except InternalTransfer.DoesNotExist:
        return JsonResponse({"error": f"Transferencia {pk} no encontrada"}, status=404)
    except TransferRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize_internal_transfer(transfer), status=200)


@csrf_exempt
@require_http_methods(["PATCH"])
def internal_transfer_reject(request, pk: int):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    comment = str(payload.get("comment") or "").strip()
    if not comment:
        return JsonResponse({"error": "Debe proporcionar un comentario"}, status=400)

    try:
        transfer = reject_transfer(pk, supervisor_user=None, comment=comment)  # TODO auth
    except InternalTransfer.DoesNotExist:
        return JsonResponse({"error": f"Transferencia {pk} no encontrada"}, status=404)
    except TransferRequestError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize_internal_transfer(transfer), status=200)
@csrf_exempt
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({'message': 'Login exitoso'})
        else:
            return JsonResponse({'error': 'Credenciales inválidas'}, status=400)
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@csrf_exempt
def logout_view(request):
    logout(request)
    return JsonResponse({'message': 'Sesión cerrada correctamente'})
