from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    SchoolViewSet, ExamResultViewSet, rankings, 
    home_data, school_detail, trigger_scrape, scrape_status
)

router = DefaultRouter()
router.register(r'schools', SchoolViewSet)
router.register(r'results', ExamResultViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/home/', home_data, name='api_home'),
    path('api/rankings/<str:exam_type>/<int:year>/', rankings, name='api_rankings'),
    path('api/school/<int:school_id>/', school_detail, name='api_school_detail'),
    path('api/scrape/', trigger_scrape, name='api_scrape'),
    path('api/scrape/status/', scrape_status, name='api_scrape_status'),
]