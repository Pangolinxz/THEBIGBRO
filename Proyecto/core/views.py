import json
import re
from datetime import date, datetime, time, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import (
    Inventory,
    InventoryAudit,
    InventoryTransaction,
    Location,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductCategory,
    PaymentMethod,
    Rol,
    StockAlert,
    StockAdjustmentRequest,
    InternalTransfer,
    TransferStatus,
    StockAdjustmentStatus,
    User,
    DeliveryAlert,
)
from domain.services.adjustments import (
    AdjustmentRequestError,
    approve_adjustment,
    create_adjustment_request,
    get_adjustment_request,
    list_adjustment_requests,
    reject_adjustment,
    get_adjustment_tolerance,
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
from domain.services.auditing import get_audit_logs
from domain.services.dashboard_metrics import get_dashboard_metrics
from domain.services.orders import (
    OrderDispatchError,
    dispatch_order,
    list_orders,
    reserve_order,
    close_order,
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

ORDER_STATUS_LABELS = {value: label for value, label in OrderStatus.choices}
TRANSACTION_TYPE_LABELS = {
    "ingreso": "Ingreso",
    "order-dispatch": "Despacho de pedido",
    "transfer-egress": "Transferencia (egreso)",
    "transfer-ingress": "Transferencia (ingreso)",
    "transfer-rejected": "Transferencia rechazada",
    "ajuste-aprobado": "Ajuste aprobado",
    "ajuste-rechazado": "Ajuste rechazado",
}
DEFAULT_ROLE_NAMES = ("Administrador", "Supervisor", "Operador de bodega")


def _generate_sku_from_prefix(prefix: str) -> str:
    normalized = prefix.strip().upper()
    if not normalized:
        raise ValueError("Debe proporcionar un prefijo para el SKU")

    base_query = Product.objects.filter(sku__startswith=f"{normalized}-").values_list("sku", flat=True)
    max_suffix = 0
    pattern = re.compile(rf"^{re.escape(normalized)}-(\d+)$")
    for sku in base_query:
        match = pattern.match(sku)
        if match:
            max_suffix = max(max_suffix, int(match.group(1)))
    next_suffix = max_suffix + 1
    return f"{normalized}-{next_suffix:04d}"


def require_role(role_name: str):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            role = getattr(request.user, "role", None)
            if request.user.is_superuser or (
                role and role.name.lower() == role_name.lower()
            ):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Requiere rol de supervisor.")

        return _wrapped

    return decorator


@login_required
def dashboard_view(request):
    sku_filter = (request.GET.get("sku") or "").strip()
    location_filter = (request.GET.get("location") or "").strip()
    date_from_str = (request.GET.get("date_from") or "").strip()
    date_to_str = (request.GET.get("date_to") or "").strip()

    product_obj = None
    location_obj = None
    default_today = timezone.localdate()
    default_start = default_today - timedelta(days=30)

    if sku_filter:
        try:
            product_obj = Product.objects.get(sku=sku_filter)
        except Product.DoesNotExist:
            messages.error(request, f"Producto {sku_filter} no encontrado.")
            sku_filter = ""

    if location_filter:
        try:
            location_obj = Location.objects.get(code=location_filter)
        except Location.DoesNotExist:
            messages.error(request, f"Ubicacion {location_filter} no encontrada.")
            location_filter = ""

    def _parse_date(value: str, default):
        if not value:
            return default
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, f"Fecha inválida: {value}")
            return default

    date_from = _parse_date(date_from_str, default_start)
    date_to = _parse_date(date_to_str, default_today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    filters = {
        "product": product_obj,
        "location": location_obj,
        "date_from": date_from,
        "date_to": date_to,
    }

    metrics = get_dashboard_metrics(filters)

    adjustments_qs = StockAdjustmentRequest.objects.filter(
        status=StockAdjustmentStatus.PENDING
    )
    if product_obj:
        adjustments_qs = adjustments_qs.filter(product=product_obj)
    if location_obj:
        adjustments_qs = adjustments_qs.filter(location=location_obj)

    transfers_qs = InternalTransfer.objects.filter(status=TransferStatus.PENDING)
    if product_obj:
        transfers_qs = transfers_qs.filter(product=product_obj)
    if location_obj:
        transfers_qs = transfers_qs.filter(
            Q(origin_location=location_obj) | Q(destination_location=location_obj)
        )

    inventory_qs = Inventory.objects.all()
    if product_obj:
        inventory_qs = inventory_qs.filter(product=product_obj)
    if location_obj:
        inventory_qs = inventory_qs.filter(location=location_obj)
    total_inventory = inventory_qs.aggregate(total=Sum("quantity")).get("total") or 0

    low_stock_items = (
        inventory_qs.select_related("product")
        .annotate(
            target_reorder=Coalesce("custom_reorder_point", "product__reorder_point")
        )
        .filter(quantity__lt=F("target_reorder"))
        .count()
    )

    transactions_qs = InventoryTransaction.objects.select_related(
        "product", "location", "user"
    ).order_by("-created_at")
    if product_obj:
        transactions_qs = transactions_qs.filter(product=product_obj)
    if location_obj:
        transactions_qs = transactions_qs.filter(location=location_obj)
    if date_from:
        transactions_qs = transactions_qs.filter(created_at__date__gte=date_from)
    if date_to:
        transactions_qs = transactions_qs.filter(created_at__date__lte=date_to)

    active_filters = []
    if product_obj:
        active_filters.append({"label": "Producto", "value": product_obj.sku})
    if location_obj:
        active_filters.append({"label": "Ubicación", "value": location_obj.code})
    if date_from or date_to:
        active_filters.append(
            {
                "label": "Fechas",
                "value": f"{date_from.isoformat()} → {date_to.isoformat()}",
            }
        )

    recent_transactions = list(transactions_qs[:5])
    for tx in recent_transactions:
        tx.display_type = _humanize_transaction_type(getattr(tx, "type", ""))

    orders_status_display = []
    for entry in metrics.get("orders_by_status", []):
        status_value = entry.get("status")
        orders_status_display.append(
            {
                "status": status_value,
                "status_label": ORDER_STATUS_LABELS.get(
                    status_value, (status_value or "").capitalize()
                ),
                "total": entry.get("total", 0),
            }
        )

    context = {
        "pending_adjustments": adjustments_qs.count(),
        "pending_transfers": transfers_qs.count(),
        "total_inventory": total_inventory,
        "total_products": metrics.get("total_products", 0),
        "low_stock_items": low_stock_items,
        "recent_transactions": recent_transactions,
        "top_products_out": metrics.get("top_products_out", []),
        "inventory_by_location": metrics.get("inventory_by_location", []),
        "ingress_today": metrics.get("ingress_today", 0),
        "egress_today": metrics.get("egress_today", 0),
        "auto_alert_count": metrics.get("auto_alert_count", 0),
        "manual_alert_count": metrics.get("manual_alert_count", 0),
        "inventory_turnover": metrics.get("inventory_turnover"),
        "fill_rate": metrics.get("fill_rate"),
        "days_of_inventory": metrics.get("days_of_inventory"),
        "orders_by_status": orders_status_display,
        "daily_movements": metrics.get("daily_movements", []),
        "movements_by_location": metrics.get("movements_by_location", []),
        "filter_values": {
            "sku": sku_filter,
            "location": location_filter,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        },
        "active_filters": active_filters,
    }
    return render(request, "dashboard.html", context)


@login_required
def ingress_view(request):
    """Display list of recent ingress records. Handle form submissions from modal."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            try:
                product_id = request.POST.get("product_id")
                location_id = request.POST.get("location_id")
                quantity = int(request.POST.get("quantity", 0))
                movement_type = request.POST.get("movement_type", "purchase")

                product = Product.objects.get(pk=product_id)
                location = Location.objects.get(pk=location_id)

                if quantity <= 0:
                    messages.error(request, "La cantidad debe ser mayor que cero.")
                else:
                    payload = {
                        "sku": product.sku,
                        "location_code": location.code,
                        "quantity": quantity,
                        "observations": f"Tipo: {movement_type}",
                    }
                    register_product_ingress(payload, created_by=request.user)
                    messages.success(request, "Ingreso registrado correctamente.")
                    return redirect("ingress-ui")
            except (Product.DoesNotExist, Location.DoesNotExist, ValueError):
                messages.error(request, "Datos inválidos para el ingreso.")
            except IngressError as exc:
                messages.error(request, str(exc))

    audits = InventoryAudit.objects.select_related("product", "location").order_by(
        "-created_at"
    )[:50]
    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "ingress.html",
        {
            "audits": audits,
            "products": products,
            "locations": locations,
        },
    )


@login_required
def ingress_create_view(request):
    """Create a new ingress record."""
    form_data = {
        "sku": "",
        "location_code": "",
        "quantity": "",
        "physical_count": "",
        "observations": "",
    }
    mismatch_info: Optional[Dict[str, int]] = None
    if request.method == "POST":
        sku = request.POST.get("sku", "").strip()
        location_code = request.POST.get("location_code", "").strip()
        quantity = request.POST.get("quantity")
        observations = request.POST.get("observations", "")
        physical_raw = request.POST.get("physical_count")
        confirm_mismatch = request.POST.get("confirm_mismatch") == "1"
        confirm_checkbox = request.POST.get("confirm_mismatch_checkbox") in {"on", "true", "1"}
        confirm_mismatch = confirm_mismatch or confirm_checkbox

        form_data.update(
            {
                "sku": sku,
                "location_code": location_code,
                "quantity": quantity,
                "physical_count": physical_raw,
                "observations": observations,
            }
        )

        try:
            physical_count = int(physical_raw)
            if physical_count < 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "La cantidad física debe ser un entero mayor o igual a 0.")
        else:
            try:
                product = Product.objects.get(sku=sku)
            except Product.DoesNotExist:
                messages.error(request, "El producto indicado no existe.")
            else:
                try:
                    location = Location.objects.get(code=location_code)
                except Location.DoesNotExist:
                    messages.error(request, "La ubicación indicada no existe.")
                else:
                    record = (
                        Inventory.objects.filter(product=product, location=location)
                        .values("quantity")
                        .first()
                    )
                    system_qty = int(record["quantity"]) if record else 0
                    try:
                        parsed_quantity = int(quantity)
                        if parsed_quantity <= 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        messages.error(request, "La cantidad a ingresar debe ser un entero mayor que 0.")
                    else:
                        delta = physical_count - system_qty
                        if delta != 0 and not confirm_mismatch:
                            mismatch_info = {
                                "system": system_qty,
                                "physical": physical_count,
                                "delta": delta,
                            }
                            messages.warning(
                                request,
                                "Hay diferencias entre el stock del sistema y el físico. Confirme para continuar.",
                            )
                        else:
                            payload = {
                                "sku": sku,
                                "location_code": location_code,
                                "quantity": parsed_quantity,
                                "observations": observations,
                            }
                            try:
                                register_product_ingress(payload, created_by=request.user)
                                if delta != 0:
                                    StockAlert.objects.create(
                                        product=product,
                                        triggered_at=timezone.now(),
                                        message=(
                                            f"Diferencia detectada en ingreso (ubicación {location.code}). "
                                            f"Sistema: {system_qty}, Físico: {physical_count}"
                                        ),
                                    )
                                    messages.info(
                                        request,
                                        "Se registró una alerta automática por diferencia de stock.",
                                    )
                                messages.success(request, "Ingreso registrado correctamente.")
                                return redirect("ingress-ui")
                            except IngressError as exc:
                                messages.error(request, str(exc))
                            except Exception as exc:
                                messages.error(request, f"No se pudo registrar el ingreso: {exc}")

    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "ingress_create.html",
        {
            "products": products,
            "locations": locations,
            "form_data": form_data,
            "mismatch_info": mismatch_info,
        },
    )


@login_required
@require_role("Supervisor")
def adjustments_view(request):
    """Display list of stock adjustments with approval/rejection actions."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            payload = {
                "sku": request.POST.get("product_id"),
                "location_code": request.POST.get("location_id"),
                "physical_quantity": request.POST.get("delta"),
                "reason": request.POST.get("reason"),
                "attachment_url": "",
            }
            try:
                # Map field names from modal form to payload
                product_id = request.POST.get("product_id")
                location_id = request.POST.get("location_id")
                delta = request.POST.get("delta")
                reason = request.POST.get("reason", "")

                product = Product.objects.get(pk=product_id)
                location = Location.objects.get(pk=location_id)

                payload["sku"] = product.sku
                payload["location_code"] = location.code
                payload["physical_quantity"] = delta
                payload["reason"] = reason

                create_adjustment_request(payload, created_by=request.user)
                messages.success(request, "Solicitud de ajuste creada.")
                return redirect("adjustments-ui")
            except (Product.DoesNotExist, Location.DoesNotExist):
                messages.error(request, "Producto o ubicación no encontrado.")
            except AdjustmentRequestError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f"Error al crear el ajuste: {exc}")
        elif action in {"approve", "reject"}:
            adjustment_id = request.POST.get("adjustment_id")
            comment = request.POST.get("comment", "")
            try:
                if action == "approve":
                    approve_adjustment(int(adjustment_id), request.user, comment)
                    messages.success(request, f"Ajuste {adjustment_id} aprobado.")
                else:
                    reject_adjustment(int(adjustment_id), request.user, comment)
                    messages.success(request, f"Ajuste {adjustment_id} rechazado.")
                return redirect("adjustments-ui")
            except AdjustmentRequestError as exc:
                messages.error(request, str(exc))
            except StockAdjustmentRequest.DoesNotExist:
                messages.error(request, "El ajuste no existe.")

    adjustments = StockAdjustmentRequest.objects.select_related(
        "product", "location", "created_by"
    ).order_by("-created_at")[:50]
    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "adjustments.html",
        {
            "adjustments": adjustments,
            "products": products,
            "locations": locations,
        },
    )


@login_required
@require_role("Supervisor")
def adjustments_create_view(request):
    """Create new stock adjustment request."""
    tolerance = get_adjustment_tolerance()

    if request.method == "POST":
        payload = {
            "sku": request.POST.get("sku"),
            "location_code": request.POST.get("location_code"),
            "physical_quantity": request.POST.get("physical_quantity"),
            "reason": request.POST.get("reason"),
            "attachment_url": request.POST.get("attachment_url", ""),
        }
        confirm_reviewed = request.POST.get("confirm_reviewed") == "1"
        if not confirm_reviewed:
            messages.error(
                request,
                "Debes confirmar que la cantidad física fue verificada antes de enviar el ajuste.",
            )
            return redirect("adjustments-create-ui")
        try:
            create_adjustment_request(payload, created_by=request.user)
            messages.success(request, "Solicitud de ajuste creada.")
            return redirect("adjustments-ui")
        except AdjustmentRequestError as exc:
            messages.error(request, str(exc))

    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "adjustments_create.html",
        {
            "products": products,
            "locations": locations,
            "tolerance": tolerance,
        },
    )


@login_required
@require_role("Supervisor")
def transfers_view(request):
    """Display list of internal transfers with approval/rejection actions."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            try:
                product_id = request.POST.get("product_id")
                origin_id = request.POST.get("origin_location_id")
                destination_id = request.POST.get("destination_location_id")
                quantity = int(request.POST.get("quantity", 0))

                product = Product.objects.get(pk=product_id)
                origin = Location.objects.get(pk=origin_id)
                destination = Location.objects.get(pk=destination_id)

                if origin == destination:
                    messages.error(request, "El origen y destino deben ser distintos.")
                elif quantity <= 0:
                    messages.error(request, "La cantidad debe ser mayor que cero.")
                else:
                    origin_inventory = (
                        Inventory.objects.filter(product=product, location=origin)
                        .values("quantity")
                        .first()
                    )
                    available = origin_inventory["quantity"] if origin_inventory else 0
                    if available < quantity:
                        messages.error(
                            request,
                            f"Inventario insuficiente en {origin.code}. Disponible: {available}.",
                        )
                    else:
                        InternalTransfer.objects.create(
                            product=product,
                            origin_location=origin,
                            destination_location=destination,
                            quantity=quantity,
                            reason="",
                            created_by=request.user,
                        )
                        messages.success(request, "Transferencia creada.")
                        return redirect("transfers-ui")
            except (Product.DoesNotExist, Location.DoesNotExist, ValueError):
                messages.error(request, "Datos inválidos para la transferencia.")
        elif action in {"approve", "reject"}:
            transfer_id = request.POST.get("transfer_id")
            comment = request.POST.get("comment", "")
            try:
                if action == "approve":
                    approve_transfer(int(transfer_id), request.user, comment)
                    messages.success(request, f"Transferencia {transfer_id} aprobada.")
                else:
                    reject_transfer(int(transfer_id), request.user, comment)
                    messages.success(request, f"Transferencia {transfer_id} rechazada.")
                return redirect("transfers-ui")
            except TransferRequestError as exc:
                messages.error(request, str(exc))
            except InternalTransfer.DoesNotExist:
                messages.error(request, "La transferencia no existe.")

    transfers = InternalTransfer.objects.select_related(
        "product", "origin_location", "destination_location", "created_by"
    ).order_by("-created_at")[:50]
    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "transfers.html",
        {"transfers": transfers, "products": products, "locations": locations},
    )


@login_required
@require_role("Supervisor")
def transfers_create_view(request):
    """Create new internal transfer."""
    if request.method == "POST":
        sku = (request.POST.get("sku") or "").strip()
        origin_code = (request.POST.get("origin_code") or "").strip()
        destination_code = (request.POST.get("destination_code") or "").strip()
        reason = request.POST.get("reason", "")
        destination_reorder_value = request.POST.get("destination_reorder_point")
        destination_reorder_point = None
        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            messages.error(request, "El producto indicado no existe.")
        else:
            try:
                origin = Location.objects.get(code=origin_code)
                destination = Location.objects.get(code=destination_code)
            except Location.DoesNotExist:
                messages.error(request, "La ubicación indicada no existe.")
            else:
                if origin == destination:
                    messages.error(request, "El origen y destino deben ser distintos.")
                else:
                    try:
                        quantity = int(request.POST.get("quantity", 0))
                        if quantity <= 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        messages.error(request, "La cantidad debe ser mayor que cero.")
                    else:
                        destination_exists = Inventory.objects.filter(
                            product=product, location=destination
                        ).exists()
                        origin_inventory = (
                            Inventory.objects.filter(product=product, location=origin)
                            .values("quantity")
                            .first()
                        )
                        available = origin_inventory["quantity"] if origin_inventory else 0
                        if available < quantity:
                            messages.error(
                                request,
                                f"Inventario insuficiente en {origin.code}. Disponible: {available}.",
                            )
                            return redirect("transfers-create-ui")
                        if destination_reorder_value not in {None, ""}:
                            try:
                                destination_reorder_point = int(destination_reorder_value)
                                if destination_reorder_point < 0:
                                    raise ValueError
                            except (TypeError, ValueError):
                                messages.error(
                                    request,
                                    "El punto de reorden destino debe ser un entero mayor o igual a 0.",
                                )
                                return redirect("transfers-create-ui")
                        if not destination_exists and destination_reorder_point is None:
                            messages.error(
                                request,
                                "Debes indicar el punto de reorden destino para una ubicación nueva.",
                            )
                            return redirect("transfers-create-ui")
                        else:
                            InternalTransfer.objects.create(
                                product=product,
                                origin_location=origin,
                                destination_location=destination,
                                quantity=quantity,
                                reason=reason,
                                created_by=request.user,
                                destination_reorder_point=destination_reorder_point,
                            )
                            messages.success(request, "Transferencia creada.")
                            return redirect("transfers-ui")

    products = Product.objects.all()
    locations = Location.objects.all()
    return render(
        request,
        "transfers_create.html",
        {"products": products, "locations": locations},
    )


@login_required
@require_role("Supervisor")
def audit_view(request):
    logs = list(get_audit_logs(request.GET)[:100])
    for record in logs:
        record.display_type = _humanize_transaction_type(getattr(record, "type", ""))
    return render(request, "audit.html", {"logs": logs})


@login_required
@require_role("Supervisor")
def alerts_view(request):
    if request.method == "POST":
        alert_id = request.POST.get("alert_id")
        if alert_id:
            deleted, _ = StockAlert.objects.filter(pk=alert_id).delete()
            if deleted:
                messages.success(request, f"Alerta {alert_id} cerrada.")
            else:
                messages.error(request, "La alerta indicada no existe.")
        else:
            messages.error(request, "Debe indicar una alerta válida.")
        return redirect("alerts-ui")

    manual_alerts = StockAlert.objects.select_related("product").order_by(
        "-triggered_at"
    )[:50]

    low_stock_qs = (
        Inventory.objects.select_related("product", "location")
        .annotate(
            target_reorder=Coalesce("custom_reorder_point", "product__reorder_point")
        )
        .filter(quantity__lt=F("target_reorder"))
        .order_by("product__sku")
    )
    auto_stock_alerts = []
    for inv in low_stock_qs:
        minimum = inv.effective_reorder_point
        auto_stock_alerts.append(
            {
                "product": inv.product,
                "location": inv.location,
                "quantity": inv.quantity,
                "minimum": minimum,
                "message": f"Stock por debajo del mínimo configurado ({minimum}).",
            }
        )

    delivery_alerts_qs = (
        DeliveryAlert.objects.select_related("order", "order__seller_id")
        .prefetch_related("order__orderitem_set")
        .order_by("-created_at")[:50]
    )
    current_time = timezone.localtime()
    delivery_alerts = []
    for alert in delivery_alerts_qs:
        order = alert.order
        due_local = timezone.localtime(alert.due_time)
        delta = due_local - current_time
        overdue = not alert.resolved and delta.total_seconds() <= 0

        if alert.resolved:
            status = "Entregado"
            countdown = "Completado"
            message = alert.message or f"Pedido #{order.id} marcado como entregado."
            note = (
                f"Confirmado {_format_local(order.actual_arrival_time)}"
                if order.actual_arrival_time
                else "Entrega confirmada."
            )
        else:
            status = "En ruta" if delta.total_seconds() > 0 else "ETA cumplida"
            countdown = _humanize_delta(delta)
            if overdue:
                message = "El pedido ya debería haber llegado. Verifica la entrega."
            else:
                message = alert.message or f"Despacho del pedido #{order.id}."
            note = None

        delivery_alerts.append(
            {
                "order": order,
                "due_local": due_local,
                "status": status,
                "message": message,
                "countdown": countdown,
                "overdue": overdue,
                "resolved": alert.resolved,
                "note": note,
            }
        )

    total_auto = len(auto_stock_alerts) + len(delivery_alerts)
    return render(
        request,
        "alerts.html",
        {
            "manual_alerts": manual_alerts,
            "auto_stock_alerts": auto_stock_alerts,
            "delivery_alerts": delivery_alerts,
            "auto_alerts_count": total_auto,
        },
    )


@login_required
@require_role("Supervisor")
def products_view(request):
    """Display product catalog and handle editing."""
    edit_product: Optional[Product] = None

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            sku_prefix_value = (request.POST.get("sku_prefix") or "").strip().upper()
            payload = {
                "name": request.POST.get("name", "").strip(),
                "description": request.POST.get("description", "").strip(),
                "category": request.POST.get("category") or ProductCategory.STANDARD,
                "reorder_point": request.POST.get("reorder_point") or 0,
                "metadata": {},
            }
            if not sku_prefix_value:
                messages.error(request, "Debe indicar el prefijo del SKU.")
            elif not payload["name"]:
                messages.error(request, "Debe indicar el nombre del producto.")
            else:
                try:
                    generated_sku = _generate_sku_from_prefix(sku_prefix_value)
                    payload["sku"] = generated_sku
                    blueprint = build_blueprint_from_payload(payload)
                    product = persist_product_from_blueprint(blueprint)
                    messages.success(
                        request,
                        f"Producto {product.sku} creado correctamente.",
                    )
                    return redirect("products-ui")
                except ValueError as exc:
                    messages.error(request, str(exc))
        elif action == "update":
            product_id = request.POST.get("product_id")
            try:
                edit_product = Product.objects.get(pk=product_id)
            except (Product.DoesNotExist, ValueError, TypeError):
                messages.error(request, "El producto indicado no existe.")
            else:
                name = request.POST.get("name_edit", "").strip()
                description = request.POST.get("description_edit", "").strip()
                category = request.POST.get("category_edit") or ProductCategory.STANDARD
                reorder_raw = request.POST.get("reorder_point_edit")
                try:
                    reorder_point = int(reorder_raw or 0)
                    if reorder_point < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    messages.error(
                        request, "El punto de reorden debe ser un entero mayor o igual a 0."
                    )
                else:
                    if not name:
                        messages.error(request, "El nombre no puede estar vacío.")
                    else:
                        edit_product.name = name
                        edit_product.description = description
                        edit_product.category = category
                        edit_product.reorder_point = reorder_point
                        edit_product.save(
                            update_fields=["name", "description", "category", "reorder_point"]
                        )
                        messages.success(
                            request, f"Producto {edit_product.sku} actualizado correctamente."
                        )
                        return redirect("products-ui")
    else:
        edit_id = request.GET.get("edit")
        if edit_id:
            try:
                edit_product = Product.objects.get(pk=edit_id)
            except Product.DoesNotExist:
                edit_product = None

    products = Product.objects.order_by("sku")[:100]
    return render(
        request,
        "products.html",
        {
            "products": products,
            "categories": ProductCategory.choices,
            "edit_product": edit_product,
        },
    )


@login_required
@require_role("Supervisor")
def products_create_view(request):
    """Create new product."""
    sku_prefix_value = ""
    sku_preview = ""

    if request.method == "POST":
        sku_prefix_value = (request.POST.get("sku_prefix") or "").strip().upper()
        payload = {
            "name": request.POST.get("name", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "category": request.POST.get("category") or ProductCategory.STANDARD,
            "reorder_point": request.POST.get("reorder_point") or 0,
            "metadata": {},
        }
        if not sku_prefix_value:
            messages.error(request, "Debe indicar el prefijo del SKU.")
        elif not payload["name"]:
            messages.error(request, "Debe indicar el nombre del producto.")
        else:
            try:
                generated_sku = _generate_sku_from_prefix(sku_prefix_value)
                payload["sku"] = generated_sku
                sku_preview = generated_sku
                blueprint = build_blueprint_from_payload(payload)
                product = persist_product_from_blueprint(blueprint)
                messages.success(
                    request,
                    f"Producto {product.sku} creado correctamente.",
                )
                return redirect("products-ui")
            except ValueError as exc:
                messages.error(request, str(exc))

    return render(
        request,
        "products_create.html",
        {
            "categories": ProductCategory.choices,
            "sku_prefix_value": sku_prefix_value,
            "sku_preview": sku_preview,
        },
    )


def _format_local(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")


def _humanize_delta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    prefix = "en "
    if total_seconds < 0:
        total_seconds = abs(total_seconds)
        prefix = "hace "
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return prefix + " ".join(parts)


def _humanize_transaction_type(raw: Optional[str]) -> str:
    if not raw:
        return "-"
    normalized = raw.strip()
    if normalized in TRANSACTION_TYPE_LABELS:
        return TRANSACTION_TYPE_LABELS[normalized]
    friendly = normalized.replace("-", " ").replace("_", " ").strip()
    return friendly.capitalize() if friendly else "-"


def _ensure_default_roles():
    for role_name in DEFAULT_ROLE_NAMES:
        Rol.objects.get_or_create(name=role_name)


@login_required
def orders_view(request):
    """Display orders with filtering, editing, and status actions (reserve, dispatch, close, delete)."""
    order_form_initial = {
        "customer_name": "",
        "customer_address": "",
        "contact_name": "",
        "contact_phone": "",
        "payment_method": PaymentMethod.CASH,
        "eta_date": "",
        "eta_time": "",
    }
    editing_order: Optional[Order] = None
    edit_items_initial: List[Dict[str, Any]] = []

    status_filter = request.GET.get("status") or OrderStatus.RESERVED
    order_id_filter = request.GET.get("order_id", "").strip()
    filters: Dict[str, str] = {}
    if status_filter and status_filter != "all":
        filters["status"] = status_filter
    if order_id_filter:
        filters["order_id"] = order_id_filter

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            customer_name = request.POST.get("customer_name", "").strip()
            customer_address = request.POST.get("customer_address", "").strip()
            contact_name = request.POST.get("contact_name", "").strip()
            contact_phone = request.POST.get("contact_phone", "").strip()
            payment_method = request.POST.get("payment_method") or PaymentMethod.CASH
            if payment_method not in dict(PaymentMethod.choices):
                payment_method = PaymentMethod.CASH

            eta_date_str = request.POST.get("eta_date", "").strip()
            eta_time_str = request.POST.get("eta_time", "").strip()
            eta_datetime = None
            if eta_date_str:
                try:
                    eta_date = datetime.strptime(eta_date_str, "%Y-%m-%d").date()
                    eta_time = (
                        datetime.strptime(eta_time_str, "%H:%M").time()
                        if eta_time_str
                        else time(0, 0)
                    )
                    eta_naive = datetime.combine(eta_date, eta_time)
                    eta_datetime = timezone.make_aware(
                        eta_naive, timezone.get_current_timezone()
                    )
                    if eta_datetime < timezone.now():
                        raise ValueError
                except ValueError:
                    messages.error(
                        request,
                        "La fecha y hora estimada de llegada deben ser válidas y posteriores al momento actual.",
                    )
                    return redirect("orders-ui")

            if not customer_name or not customer_address or not contact_name or not contact_phone:
                messages.error(request, "Todos los campos de cliente son obligatorios.")
            else:
                order = Order.objects.create(
                    seller_id=request.user if request.user.is_authenticated else None,
                    status=OrderStatus.CREATED,
                    customer_name=customer_name,
                    customer_address=customer_address,
                    contact_name=contact_name,
                    contact_phone=contact_phone,
                    payment_method=payment_method,
                    estimated_arrival_time=eta_datetime,
                )
                messages.success(request, f"Pedido {order.id} creado correctamente.")
                return redirect("orders-ui")
        elif action == "update-order":
            order_id_raw = request.POST.get("order_id")
            try:
                order_id_int = int(order_id_raw)
            except (TypeError, ValueError):
                messages.error(request, "El identificador del pedido no es válido.")
                return redirect("orders-ui")

            edit_url = f"{reverse('orders-ui')}?edit_order={order_id_int}"
            try:
                order = Order.objects.get(pk=order_id_int)
            except Order.DoesNotExist:
                messages.error(request, "El pedido indicado no existe.")
                return redirect("orders-ui")

            if order.status not in {OrderStatus.CREATED, OrderStatus.RESERVED}:
                messages.error(
                    request,
                    "Solo puedes editar pedidos en estado CREADO o RESERVADO.",
                )
                return redirect("orders-ui")

            customer_name = request.POST.get("customer_name", "").strip()
            customer_address = request.POST.get("customer_address", "").strip()
            contact_name = request.POST.get("contact_name", "").strip()
            contact_phone = request.POST.get("contact_phone", "").strip()
            payment_method = request.POST.get("payment_method") or PaymentMethod.CASH
            if payment_method not in dict(PaymentMethod.choices):
                payment_method = PaymentMethod.CASH

            eta_date_str = request.POST.get("eta_date", "").strip()
            eta_time_str = request.POST.get("eta_time", "").strip()
            eta_datetime = None
            if eta_date_str:
                try:
                    eta_date = datetime.strptime(eta_date_str, "%Y-%m-%d").date()
                    eta_time = (
                        datetime.strptime(eta_time_str, "%H:%M").time()
                        if eta_time_str
                        else time(0, 0)
                    )
                    eta_naive = datetime.combine(eta_date, eta_time)
                    eta_datetime = timezone.make_aware(
                        eta_naive, timezone.get_current_timezone()
                    )
                    if eta_datetime < timezone.now():
                        raise ValueError
                except ValueError:
                    messages.error(
                        request,
                        "La fecha y hora estimada de llegada deben ser válidas y posteriores al momento actual.",
                    )
                    return redirect(edit_url)

            item_skus = request.POST.getlist("item_sku[]")
            item_locations = request.POST.getlist("item_location[]")
            item_quantities = request.POST.getlist("item_quantity[]")
            if not item_skus:
                messages.error(request, "Debes agregar al menos un producto al pedido.")
                return redirect(edit_url)

            valid_items = []
            for sku, loc_code, qty_raw in zip(
                item_skus, item_locations, item_quantities
            ):
                sku = sku.strip()
                loc_code = loc_code.strip()
                if not sku or not loc_code:
                    continue
                try:
                    product = Product.objects.get(sku=sku)
                except Product.DoesNotExist:
                    messages.error(request, f"Producto {sku} no existe.")
                    return redirect(edit_url)
                try:
                    location = Location.objects.get(code=loc_code)
                except Location.DoesNotExist:
                    messages.error(request, f"Ubicación {loc_code} no existe.")
                    return redirect(edit_url)
                try:
                    quantity = int(qty_raw or 0)
                    if quantity <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    messages.error(
                        request, "Las cantidades deben ser enteros positivos."
                    )
                    return redirect(edit_url)
                valid_items.append((product, location, quantity))

            if not valid_items:
                messages.error(
                    request, "No se pudo registrar ningún ítem válido para el pedido."
                )
                return redirect(edit_url)

            was_reserved = False
            try:
                with transaction.atomic():
                    order_locked = (
                        Order.objects.select_for_update()
                        .prefetch_related("orderitem_set")
                        .get(pk=order_id_int)
                    )
                    if order_locked.status not in {
                        OrderStatus.CREATED,
                        OrderStatus.RESERVED,
                    }:
                        raise OrderDispatchError(
                            "El pedido cambió de estado y ya no puede editarse."
                        )
                    was_reserved = order_locked.status == OrderStatus.RESERVED

                    OrderItem.objects.filter(order=order_locked).delete()
                    OrderItem.objects.bulk_create(
                        [
                            OrderItem(
                                order=order_locked,
                                product=product,
                                location=location,
                                quantity=quantity,
                                reserved=False,
                            )
                            for product, location, quantity in valid_items
                        ]
                    )

                    order_locked.customer_name = customer_name
                    order_locked.customer_address = customer_address
                    order_locked.contact_name = contact_name
                    order_locked.contact_phone = contact_phone
                    order_locked.payment_method = payment_method
                    order_locked.estimated_arrival_time = eta_datetime
                    order_locked.status = OrderStatus.CREATED
                    order_locked.save(
                        update_fields=[
                            "customer_name",
                            "customer_address",
                            "contact_name",
                            "contact_phone",
                            "payment_method",
                            "estimated_arrival_time",
                            "status",
                        ]
                    )
            except Order.DoesNotExist:
                messages.error(request, "El pedido indicado no existe.")
                return redirect("orders-ui")
            except OrderDispatchError as exc:
                messages.error(request, str(exc))
                return redirect(edit_url)

            messages.success(
                request, f"Pedido {order_id_int} actualizado correctamente."
            )
            if was_reserved:
                try:
                    reserve_order(order_id_int, request.user)
                    messages.success(
                        request,
                        f"Pedido {order_id_int} volvió a reservase automáticamente.",
                    )
                except OrderDispatchError as exc:
                    messages.warning(
                        request,
                        (
                            f"Pedido {order_id_int} actualizado, "
                            f"pero no se pudo reservar nuevamente: {exc}"
                        ),
                    )
            return redirect("orders-ui")
        elif action == "reserve":
            order_id = request.POST.get("order_id")
            try:
                reserve_order(int(order_id), request.user)
                messages.success(request, f"Pedido {order_id} reservado correctamente.")
            except (Order.DoesNotExist, ValueError, TypeError):
                messages.error(request, "El pedido indicado no existe.")
            except OrderDispatchError as exc:
                messages.error(request, str(exc))
            return redirect("orders-ui")
        elif action == "dispatch":
            order_id = request.POST.get("order_id")
            try:
                dispatch_order(int(order_id), request.user)
                messages.success(
                    request,
                    f"Pedido {order_id} despachado correctamente. "
                    "Se inició la cuenta regresiva de entrega.",
                )
            except (Order.DoesNotExist, ValueError, TypeError):
                messages.error(request, "El pedido indicado no existe.")
            except OrderDispatchError as exc:
                messages.error(request, str(exc))
            return redirect("orders-ui")
        elif action == "close":
            order_id = request.POST.get("order_id")
            try:
                close_order(int(order_id), request.user)
                messages.success(
                    request, f"Pedido {order_id} cerrado. Entrega confirmada."
                )
            except (Order.DoesNotExist, ValueError, TypeError):
                messages.error(request, "El pedido indicado no existe.")
            except OrderDispatchError as exc:
                messages.error(request, str(exc))
            return redirect("orders-ui")
        elif action == "delete":
            order_id = request.POST.get("order_id")
            try:
                order = Order.objects.get(pk=order_id)
            except (Order.DoesNotExist, ValueError, TypeError):
                messages.error(request, "El pedido indicado no existe.")
            else:
                if order.status in {OrderStatus.DISPATCHED, OrderStatus.CLOSED}:
                    messages.error(
                        request,
                        "No se puede eliminar un pedido que ya fue despachado o cerrado.",
                    )
                else:
                    order.delete()
                    messages.success(request, f"Pedido {order_id} eliminado del sistema.")
            return redirect("orders-ui")

    edit_order_id = request.GET.get("edit_order")
    if edit_order_id:
        try:
            edit_order_int = int(edit_order_id)
        except (TypeError, ValueError):
            messages.error(request, "El pedido indicado no es válido.")
            return redirect("orders-ui")
        try:
            editing_order = (
                Order.objects.prefetch_related(
                    "orderitem_set__product",
                    "orderitem_set__location",
                ).get(pk=edit_order_int)
            )
        except Order.DoesNotExist:
            messages.error(request, "El pedido indicado no existe.")
            return redirect("orders-ui")
        if editing_order.status not in {OrderStatus.CREATED, OrderStatus.RESERVED}:
            messages.error(
                request,
                "Solo puedes editar pedidos en estado CREADO o RESERVADO.",
            )
            return redirect("orders-ui")

        order_form_initial.update(
            {
                "customer_name": editing_order.customer_name,
                "customer_address": editing_order.customer_address,
                "contact_name": editing_order.contact_name,
                "contact_phone": editing_order.contact_phone,
                "payment_method": editing_order.payment_method,
            }
        )
        if editing_order.estimated_arrival_time:
            eta_local = timezone.localtime(editing_order.estimated_arrival_time)
            order_form_initial["eta_date"] = eta_local.strftime("%Y-%m-%d")
            order_form_initial["eta_time"] = eta_local.strftime("%H:%M")
        else:
            order_form_initial["eta_date"] = ""
            order_form_initial["eta_time"] = ""

        edit_items_initial = [
            {
                "sku": item.product.sku,
                "location": item.location.code if item.location else "",
                "quantity": item.quantity,
            }
            for item in editing_order.orderitem_set.all()
        ]

    orders_qs = list_orders(filters).order_by("-created_at")[:50]
    current_time = timezone.localtime()

    tracking_rows = []
    for order in orders_qs:
        alert = getattr(order, "delivery_alert", None)
        due_local = None
        countdown = None
        overdue = False
        if alert and alert.due_time:
            due_local = timezone.localtime(alert.due_time)
            countdown = _humanize_delta(due_local - current_time)
            overdue = (due_local - current_time).total_seconds() < 0 and not alert.resolved
        elif order.status == OrderStatus.DISPATCHED and not alert:
            countdown = "En ruta (sin ETA)"

        if order.status == OrderStatus.CLOSED and order.actual_arrival_time:
            tracking_message = f"Entregado el {_format_local(order.actual_arrival_time)}"
        elif overdue:
            tracking_message = "La entrega está vencida. Verificar con transporte."
        elif order.status == OrderStatus.DISPATCHED:
            tracking_message = (
                "En ruta y monitoreado." if countdown else "En ruta (sin alerta activa)."
            )
        elif order.status == OrderStatus.RESERVED:
            tracking_message = "Stock reservado. Listo para despacho."
        else:
            tracking_message = "Pendiente por reservar."

        tracking_rows.append(
            {
                "order": order,
                "alert": alert,
                "due_local": due_local,
                "countdown": countdown,
                "overdue": overdue,
                "tracking_message": tracking_message,
            }
        )

    guidance_steps = [
        ("1. Crear", "Diligencia cliente, dirección, productos y ETA opcional."),
        ("2. Reservar", "Valida stock en la ubicación elegida antes de confirmar."),
        ("3. Despachar", "Confirma verificación física. Se descuenta inventario y arranca la alerta."),
        ("4. Cerrar", "Cuando el cliente confirma recepción, marca el pedido como cerrado."),
    ]

    return render(
        request,
        "orders.html",
        {
            "orders": orders_qs,
            "orders_tracking": tracking_rows,
            "status_filter": status_filter,
            "order_id_filter": order_id_filter,
            "status_choices": OrderStatus.choices,
            "payment_choices": PaymentMethod.choices,
            "now": current_time,
            "guidance_steps": guidance_steps,
            "editing_order": editing_order,
            "order_form": order_form_initial,
            "edit_items": edit_items_initial,
        },
    )


@login_required
def orders_create_view(request):
    """Create new order."""
    if request.method == "POST":
        customer_name = request.POST.get("customer_name", "").strip()
        customer_address = request.POST.get("customer_address", "").strip()
        contact_name = request.POST.get("contact_name", "").strip()
        contact_phone = request.POST.get("contact_phone", "").strip()
        payment_method = request.POST.get("payment_method") or PaymentMethod.CASH
        if payment_method not in dict(PaymentMethod.choices):
            payment_method = PaymentMethod.CASH
        requested_status = request.POST.get("status_new") or OrderStatus.CREATED
        if requested_status not in dict(OrderStatus.choices):
            requested_status = OrderStatus.CREATED

        eta_date_str = request.POST.get("eta_date", "").strip()
        eta_time_str = request.POST.get("eta_time", "").strip()
        eta_datetime = None
        if eta_date_str:
            try:
                eta_date = datetime.strptime(eta_date_str, "%Y-%m-%d").date()
                eta_time = (
                    datetime.strptime(eta_time_str, "%H:%M").time()
                    if eta_time_str
                    else time(0, 0)
                )
                eta_naive = datetime.combine(eta_date, eta_time)
                eta_datetime = timezone.make_aware(
                    eta_naive, timezone.get_current_timezone()
                )
                if eta_datetime < timezone.now():
                    raise ValueError
            except ValueError:
                messages.error(
                    request,
                    "La fecha y hora estimada de llegada deben ser válidas y posteriores al momento actual.",
                )
                return redirect("orders-create-ui")

        item_skus = request.POST.getlist("item_sku[]")
        item_locations = request.POST.getlist("item_location[]")
        item_quantities = request.POST.getlist("item_quantity[]")
        if not item_skus:
            messages.error(request, "Debes agregar al menos un producto al pedido.")
            return redirect("orders-create-ui")
        valid_items = []
        for sku, loc_code, qty_raw in zip(item_skus, item_locations, item_quantities):
            sku = sku.strip()
            loc_code = loc_code.strip()
            if not sku or not loc_code:
                continue
            try:
                product = Product.objects.get(sku=sku)
            except Product.DoesNotExist:
                messages.error(request, f"Producto {sku} no existe.")
                return redirect("orders-create-ui")
            try:
                location = Location.objects.get(code=loc_code)
            except Location.DoesNotExist:
                messages.error(request, f"Ubicación {loc_code} no existe.")
                return redirect("orders-create-ui")
            try:
                quantity = int(qty_raw or 0)
                if quantity <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                messages.error(request, "Las cantidades deben ser enteros positivos.")
                return redirect("orders-create-ui")
            valid_items.append((product, location, quantity))
        if not valid_items:
            messages.error(request, "No se pudo registrar ningún ítem válido.")
            return redirect("orders-create-ui")
        order = Order.objects.create(
            seller_id=request.user if request.user.is_authenticated else None,
            status=OrderStatus.CREATED,
            customer_name=customer_name,
            customer_address=customer_address,
            contact_name=contact_name,
            contact_phone=contact_phone,
            payment_method=payment_method,
            estimated_arrival_time=eta_datetime,
        )
        bulk = [
            OrderItem(
                order=order,
                product=product,
                location=location,
                quantity=quantity,
                reserved=False,
            )
            for product, location, quantity in valid_items
        ]
        OrderItem.objects.bulk_create(bulk)
        if requested_status == OrderStatus.RESERVED:
            try:
                reserve_order(order.id, request.user)
                messages.success(
                    request,
                    f"Pedido {order.id} creado y reservado correctamente.",
                )
            except OrderDispatchError as exc:
                messages.error(
                    request,
                    f"Pedido {order.id} creado, pero no se pudo reservar: {exc}",
                )
        else:
            messages.success(request, f"Pedido {order.id} creado correctamente.")
        return redirect("orders-ui")

    order_form_initial = {
        "customer_name": "",
        "customer_address": "",
        "contact_name": "",
        "contact_phone": "",
        "payment_method": PaymentMethod.CASH,
        "eta_date": "",
        "eta_time": "",
    }

    guidance_steps = [
        ("1. Crear", "Diligencia cliente, dirección, productos y ETA opcional."),
        ("2. Reservar", "Valida stock en la ubicación elegida antes de confirmar."),
        ("3. Despachar", "Confirma verificación física. Se descuenta inventario y arranca la alerta."),
        ("4. Cerrar", "Cuando el cliente confirma recepción, marca el pedido como cerrado."),
    ]

    return render(
        request,
        "orders_create.html",
        {
            "status_choices": OrderStatus.choices,
            "payment_choices": PaymentMethod.choices,
            "order_form": order_form_initial,
            "guidance_steps": guidance_steps,
        },
    )


@login_required
@require_role("Supervisor")
@login_required
@require_role("Supervisor")
def users_view(request):
    """Display list of users. Handle user creation from modal."""
    _ensure_default_roles()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            username = request.POST.get("username", "").strip()
            email = request.POST.get("email", "").strip()
            full_name = request.POST.get("full_name", "").strip()
            password1 = request.POST.get("password1", "")
            password2 = request.POST.get("password2", "")
            role_id = request.POST.get("role_id")

            if not all([username, email, full_name, password1]):
                messages.error(request, "Todos los campos son obligatorios.")
            elif password1 != password2:
                messages.error(request, "Las contraseñas no coinciden.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, "El nombre de usuario ya existe.")
            else:
                try:
                    role = Rol.objects.get(pk=role_id) if role_id else None
                    User.objects.create_user(
                        username=username,
                        email=email,
                        password=password1,
                        full_name=full_name,
                        role=role,
                    )
                    messages.success(request, f"Usuario {username} creado correctamente.")
                    return redirect("users-ui")
                except Rol.DoesNotExist:
                    messages.error(request, "El rol seleccionado no existe.")
                except Exception as exc:
                    messages.error(request, f"Error al crear usuario: {exc}")

    users = User.objects.select_related("role").order_by("username")[:100]
    roles = Rol.objects.order_by("name")
    return render(request, "users.html", {"users": users, "roles": roles})


@login_required
@require_role("Supervisor")
def locations_view(request):
    edit_location: Optional[Location] = None

    def _parse_capacity(raw_value: Optional[str]) -> int:
        try:
            capacity = int(raw_value or 0)
        except (TypeError, ValueError):
            raise ValueError("La capacidad debe ser un número entero")
        if capacity <= 0:
            raise ValueError("La capacidad debe ser mayor que 0")
        return capacity

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            code = (request.POST.get("code") or "").strip()
            description = (request.POST.get("description") or "").strip()
            capacity_input = request.POST.get("capacity")
            try:
                capacity = _parse_capacity(capacity_input)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                if not code:
                    messages.error(request, "El código es obligatorio.")
                elif Location.objects.filter(code=code).exists():
                    messages.error(request, "Ya existe una ubicación con ese código.")
                else:
                    Location.objects.create(
                        code=code,
                        description=description,
                        capacity=capacity,
                        is_active=True,
                    )
                    messages.success(request, f"Ubicación {code} creada correctamente.")
                    return redirect("locations-ui")

        elif action == "update":
            location_id = request.POST.get("location_id")
            try:
                edit_location = Location.objects.get(pk=location_id)
            except Location.DoesNotExist:
                messages.error(request, "La ubicación seleccionada no existe.")
            else:
                new_code = (request.POST.get("code") or "").strip()
                description = (request.POST.get("description") or "").strip()
                is_active = request.POST.get("is_active") == "on"
                try:
                    capacity = _parse_capacity(request.POST.get("capacity"))
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    if not new_code:
                        messages.error(request, "El código no puede estar vacío.")
                    elif (
                        Location.objects.filter(code=new_code)
                        .exclude(pk=edit_location.pk)
                        .exists()
                    ):
                        messages.error(request, "Ya existe otra ubicación con ese código.")
                    else:
                        edit_location.code = new_code
                        edit_location.description = description
                        edit_location.capacity = capacity
                        edit_location.is_active = is_active
                        edit_location.save(
                            update_fields=[
                                "code",
                                "description",
                                "capacity",
                                "is_active",
                            ]
                        )
                        messages.success(request, "Ubicación actualizada correctamente.")
                        return redirect("locations-ui")
        elif action == "toggle":
            location_id = request.POST.get("location_id")
            try:
                location = Location.objects.get(pk=location_id)
            except Location.DoesNotExist:
                messages.error(request, "La ubicación indicada no existe.")
            else:
                location.is_active = not location.is_active
                location.save(update_fields=["is_active"])
                state = "activada" if location.is_active else "desactivada"
                messages.success(request, f"Ubicación {location.code} {state}.")
                return redirect("locations-ui")
        elif action == "delete":
            location_id = request.POST.get("location_id")
            try:
                location = Location.objects.get(pk=location_id)
            except Location.DoesNotExist:
                messages.error(request, "La ubicación indicada no existe.")
            else:
                if Inventory.objects.filter(location=location).exists():
                    messages.error(
                        request,
                        "No se puede eliminar: la ubicación tiene inventario asociado.",
                    )
                else:
                    try:
                        location.delete()
                        messages.success(request, "Ubicación eliminada correctamente.")
                    except ProtectedError:
                        messages.error(
                            request, "No se puede eliminar la ubicación (referencias activas)."
                        )
                return redirect("locations-ui")
    else:
        edit_id = request.GET.get("edit")
        if edit_id:
            try:
                edit_location = Location.objects.get(pk=edit_id)
            except Location.DoesNotExist:
                edit_location = None

    locations = (
        Location.objects.order_by("code")
        .annotate(
            has_inventory=Exists(
                Inventory.objects.filter(location=OuterRef("pk"))
            )
        )[:200]
    )
    return render(
        request,
        "locations.html",
        {"locations": locations, "edit_location": edit_location},
    )


@login_required
def product_autocomplete(request):
    query = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 25))

    queryset = Product.objects.all()
    if query:
        queryset = queryset.filter(Q(sku__icontains=query) | Q(name__icontains=query))
    products = queryset.order_by("sku")[:limit]

    items = [
        {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "label": f"{product.sku} - {product.name}",
        }
        for product in products
    ]
    return JsonResponse({"items": items, "count": len(items)})


@login_required
def system_quantity_api(request):
    sku = (request.GET.get("sku") or "").strip()
    location_code = (request.GET.get("location") or "").strip()
    if not sku or not location_code:
        return JsonResponse({"error": "Debe enviar sku y location"}, status=400)
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Producto no encontrado"}, status=404)
    try:
        location = Location.objects.get(code=location_code)
    except Location.DoesNotExist:
        return JsonResponse({"error": "Ubicacion no encontrada"}, status=404)

    record = (
        Inventory.objects.filter(product=product, location=location)
        .values("quantity", "updated_at")
        .first()
    )
    quantity = int(record["quantity"]) if record else 0
    updated_at = record["updated_at"].isoformat() if record and record["updated_at"] else None
    return JsonResponse({"quantity": quantity, "updated_at": updated_at})


@login_required
def location_autocomplete(request):
    query = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 25))

    queryset = Location.objects.all()
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query) | Q(description__icontains=query)
        )
    locations = queryset.order_by("code")[:limit]
    items = [
        {
            "id": location.id,
            "code": location.code,
            "description": location.description,
            "label": f"{location.code} - {location.description or ''}".strip(),
        }
        for location in locations
    ]
    return JsonResponse({"items": items, "count": len(items)})


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
def audit_movements(request):
    if request.method != "GET":
        return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)

    filters = {
        "date_from": request.GET.get("date_from"),
        "date_to": request.GET.get("date_to"),
        "user_id": request.GET.get("user_id"),
        "product_id": request.GET.get("product_id"),
        "location_id": request.GET.get("location_id"),
        "action": request.GET.get("action"),
        "ordering": request.GET.get("ordering"),
    }
    queryset = get_audit_logs(filters)
    items = [
        {
            "id": tx.id,
            "product": tx.product.sku if tx.product else None,
            "location": tx.location.code if tx.location else None,
            "user": tx.user.username if tx.user else None,
            "type": tx.type,
            "quantity": tx.quantity,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in queryset
    ]
    return JsonResponse({"items": items, "count": len(items)}, status=200)


@csrf_exempt
def audit_movements_export(request):
    if request.method != "GET":
        return JsonResponse({"error": f"Metodo {request.method} no permitido"}, status=405)

    queryset = get_audit_logs(request.GET)
    rows = []
    rows.append(
        """
        <tr style="background-color:#198754;color:#ffffff;">
            <th>ID</th>
            <th>Producto</th>
            <th>Ubicación</th>
            <th>Usuario</th>
            <th>Acción</th>
            <th>Cantidad</th>
            <th>Fecha</th>
        </tr>
        """
    )
    for tx in queryset:
        rows.append(
            f"""
            <tr>
                <td style="text-align:center;">{tx.id}</td>
                <td>{tx.product.sku if tx.product else ""}</td>
                <td>{tx.location.code if tx.location else ""}</td>
                <td>{tx.user.username if tx.user else ""}</td>
                <td>{_humanize_transaction_type(getattr(tx, "type", ""))}</td>
                <td style="text-align:right;">{tx.quantity}</td>
                <td>{timezone.localtime(tx.created_at).strftime("%Y-%m-%d %H:%M") if tx.created_at else ""}</td>
            </tr>
            """
        )

    table_html = f"""
        <html>
            <head>
                <meta charset="utf-8">
                <style>
                    table {{
                        border-collapse: collapse;
                        width: 100%;
                    }}
                    th, td {{
                        border: 1px solid #dee2e6;
                        padding: 6px;
                    }}
                    tr:nth-child(odd) td {{
                        background-color: #f8f9fa;
                    }}
                </style>
            </head>
            <body>
                <table>
                    {''.join(rows)}
                </table>
            </body>
        </html>
    """
    filename = timezone.now().strftime("auditoria_movimientos_%Y%m%d_%H%M%S.xls")
    return HttpResponse(
        "\ufeff" + table_html,
        content_type="application/vnd.ms-excel; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@login_required
@require_role("Supervisor")
def alerts_api(request):
    alerts = (
        Inventory.objects.select_related("product", "location")
        .annotate(
            target_reorder=Coalesce("custom_reorder_point", "product__reorder_point")
        )
        .filter(quantity__lt=F("target_reorder"))
        .order_by("product__sku")
    )
    now = timezone.now()
    data = []
    for inv in alerts:
        reorder_point = inv.effective_reorder_point
        deficit = max(reorder_point - inv.quantity, 0)
        hours_open = None
        if inv.updated_at:
            delta = now - inv.updated_at
            hours_open = round(delta.total_seconds() / 3600, 1)
        data.append(
            {
                "product": inv.product.sku,
                "product_name": inv.product.name,
                "location": inv.location.code,
                "location_name": inv.location.description,
                "quantity": inv.quantity,
                "reorder_point": reorder_point,
                "deficit": deficit,
                "hours_open": hours_open,
            }
        )
    return JsonResponse({"items": data, "count": len(data)})


@login_required
@require_role("Administrador")
def registration_view(request):
    """Admin-only user registration/creation page."""
    _ensure_default_roles()
    roles = Rol.objects.order_by("name")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password") or ""
        password_confirm = request.POST.get("password_confirm") or ""
        role_id = request.POST.get("role_id")

        # Validation
        if not username or not email or not password:
            messages.error(request, "Usuario, correo y contraseña son obligatorios.")
        elif password != password_confirm:
            messages.error(request, "Las contraseñas no coinciden.")
        elif len(password) < 8:
            messages.error(request, "La contraseña debe tener al menos 8 caracteres.")
        elif not role_id:
            messages.error(request, "Debes seleccionar un rol para el usuario.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Ya existe un usuario con ese nombre.")
        elif User.objects.filter(email=email).exists():
            messages.error(request, "Ya existe un usuario con ese correo.")
        else:
            try:
                role = Rol.objects.get(pk=role_id)
            except Rol.DoesNotExist:
                messages.error(request, "El rol seleccionado no existe.")
                return redirect("registration-ui")

            user = User.objects.create_user(username=username, email=email, password=password)
            user.first_name = first_name
            user.last_name = last_name
            user.full_name = full_name
            user.role = role
            user.save(update_fields=["first_name", "last_name", "full_name", "role"])
            messages.success(request, f"Usuario {username} creado correctamente.")
            return redirect("registration-ui")

    return render(request, "registration/register.html", {"roles": roles})


@login_required
def settings_view(request):
    """User settings page for theme customization and user information."""
    return render(request, "settings.html")
