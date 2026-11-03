"""
URL configuration for ecom project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from sanjilas import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("sanjilas.urls")),
    path("llms.txt", views.llms, name="llms-txt"),
    path("llms-full.txt", views.llms, {"full": True}, name="llms-full-txt"),
    path("", views.storefront, name="storefront"),
    path("products/<slug:product_slug>/", views.storefront, name="product"),
    path("login/", views.storefront, name="login"),
    path("account/", views.storefront, name="account"),
    path("invoice/<uuid:order_id>/", views.storefront, name="invoice"),
    path("control/", views.storefront, name="react-control"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static("/assets/", document_root=settings.BASE_DIR.parent / "frontend" / "dist" / "assets")
