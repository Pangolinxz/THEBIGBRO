from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/db/', views.database_health, name='database-health'),
    path('products/factory/', views.product_factory, name='product-factory'),
    path('api/<slug:model_key>/', views.crud_collection, name='crud-collection'),
    path('api/<slug:model_key>/<int:pk>/', views.crud_resource, name='crud-resource'),
]
