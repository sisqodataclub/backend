from django.contrib import admin
from django.urls import path, include  # <--- Added 'include' here

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('products.urls')),
    # When you are ready for services, uncomment the line below:
    # path('api/', include('services.urls')), 
]

