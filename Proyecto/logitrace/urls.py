from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/db/', views.database_health, name='database-health'),
    path('products/factory/', views.product_factory, name='product-factory'),
    path('inventory/ingress/', views.inventory_ingress, name='inventory-ingress'),
    path('inventory/adjustments/', views.adjustment_requests, name='adjustment-requests'),
    path('inventory/adjustments/<int:pk>/', views.adjustment_request_detail, name='adjustment-request-detail'),
    path('api/<slug:model_key>/', views.crud_collection, name='crud-collection'),
    path('api/<slug:model_key>/<int:pk>/', views.crud_resource, name='crud-resource'),
]
