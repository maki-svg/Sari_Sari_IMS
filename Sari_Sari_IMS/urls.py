from django.contrib import admin
from django.urls import path, include
from user import views as user_views  # Import user views
from django.contrib.auth import views as auth_views  # Import Django auth views
from user.views import logout_view  # Import correct views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', auth_views.LoginView.as_view(template_name='user/login.html'), name='user-login'),
    path('register/', user_views.register, name='user-register'),
    path('logout/', logout_view, name='user-logout'),
    path('profile/', login_required(user_views.profile), name='user-profile'),
    path('profile/update/', login_required(user_views.profile_update), name='user-profile-update'),
    path('dashboard/', include('dashboard.urls')),  # All dashboard URLs will be under /dashboard/
] 

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
