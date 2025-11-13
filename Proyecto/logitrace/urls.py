from django.contrib import admin
from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView

from core import views

urlpatterns = [
    path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', views.dashboard_view, name='dashboard'),
    path('admin/', admin.site.urls),
    path('health/db/', views.database_health, name='database-health'),
    path('products/factory/', views.product_factory, name='product-factory'),
    path('inventory/ingress/', views.inventory_ingress, name='inventory-ingress'),
    path('ui/ingress/', views.ingress_view, name='ingress-ui'),
    path('ui/adjustments/', views.adjustments_view, name='adjustments-ui'),
    path('ui/transfers/', views.transfers_view, name='transfers-ui'),
    path('ui/audit/', views.audit_view, name='audit-ui'),
    path('ui/alerts/', views.alerts_view, name='alerts-ui'),
    path('ui/orders/', views.orders_view, name='orders-ui'),
    path('ui/products/', views.products_view, name='products-ui'),
    path('ui/users/', views.users_view, name='users-ui'),
    path('ui/locations/', views.locations_view, name='locations-ui'),
    path('inventory/adjustments/', views.adjustment_requests, name='adjustment-requests'),
    path('inventory/adjustments/<int:pk>/', views.adjustment_request_detail, name='adjustment-request-detail'),
    path('inventory/adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment-approve'),
    path('inventory/adjustments/<int:pk>/reject/', views.adjustment_reject, name='adjustment-reject'),
    path('transfers/internal/pending/', views.internal_transfers_pending, name='internal-transfers-pending'),
    path('transfers/internal/<int:pk>/', views.internal_transfer_detail, name='internal-transfer-detail'),
    path('transfers/internal/<int:pk>/approve/', views.internal_transfer_approve, name='internal-transfer-approve'),
    path('transfers/internal/<int:pk>/reject/', views.internal_transfer_reject, name='internal-transfer-reject'),
    path('audit/movements/', views.audit_movements, name='audit-movements'),
    path('audit/movements/export/', views.audit_movements_export, name='audit-movements-export'),
    path('alerts/auto/', views.alerts_api, name='alerts-api'),
    path('api/autocomplete/products/', views.product_autocomplete, name='products-autocomplete'),
    path('api/autocomplete/locations/', views.location_autocomplete, name='locations-autocomplete'),
    path('api/inventory/system-quantity/', views.system_quantity_api, name='system-quantity-api'),
    path('api/<slug:model_key>/', views.crud_collection, name='crud-collection'),
    path('api/<slug:model_key>/<int:pk>/', views.crud_resource, name='crud-resource'),
]
