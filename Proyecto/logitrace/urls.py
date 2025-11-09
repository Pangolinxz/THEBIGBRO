from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('admin/', admin.site.urls),
    path('health/db/', views.database_health, name='database-health'),
    path('products/factory/', views.product_factory, name='product-factory'),
    path('inventory/ingress/', views.inventory_ingress, name='inventory-ingress'),
    path('inventory/adjustments/', views.adjustment_requests, name='adjustment-requests'),
    path('inventory/adjustments/<int:pk>/', views.adjustment_request_detail, name='adjustment-request-detail'),
    path('inventory/adjustments/<int:pk>/approve/', views.adjustment_approve, name='adjustment-approve'),
    path('inventory/adjustments/<int:pk>/reject/', views.adjustment_reject, name='adjustment-reject'),
    path('transfers/internal/pending/', views.internal_transfers_pending, name='internal-transfers-pending'),
    path('transfers/internal/<int:pk>/', views.internal_transfer_detail, name='internal-transfer-detail'),
    path('transfers/internal/<int:pk>/approve/', views.internal_transfer_approve, name='internal-transfer-approve'),
    path('transfers/internal/<int:pk>/reject/', views.internal_transfer_reject, name='internal-transfer-reject'),
    path('api/<slug:model_key>/', views.crud_collection, name='crud-collection'),
    path('api/<slug:model_key>/<int:pk>/', views.crud_resource, name='crud-resource'),
]
