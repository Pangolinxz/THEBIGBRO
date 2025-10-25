from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/db/', views.database_health, name='database-health'),
    path('products/factory/', views.product_factory, name='product-factory'),
]
