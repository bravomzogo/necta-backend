from rest_framework import viewsets, generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django.shortcuts import get_object_or_404
from .models import School, ExamResult
from .serializers import SchoolSerializer, ExamResultSerializer

class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer

class ExamResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExamResult.objects.select_related('school')
    serializer_class = ExamResultSerializer
    
    def get_queryset(self):
        queryset = ExamResult.objects.select_related('school')
        exam_type = self.request.query_params.get('exam_type')
        year = self.request.query_params.get('year')
        region = self.request.query_params.get('region')
        
        if exam_type:
            queryset = queryset.filter(exam=exam_type.upper())
        if year:
            queryset = queryset.filter(year=year)
        if region:
            queryset = queryset.filter(school__region__iexact=region)
            
        return queryset.order_by("gpa", "-total")

@api_view(['GET'])
def rankings(request, exam_type, year):
    results = ExamResult.objects.filter(
        exam=exam_type.upper(), 
        year=year,
        gpa__gt=0
    ).select_related('school').order_by("gpa", "-total")
    
    # Calculate statistics
    total_schools = results.count()
    total_students = results.aggregate(total=Sum('total'))['total'] or 0
    
    valid_results = results.exclude(gpa=0)
    avg_gpa_all = valid_results.aggregate(avg=Avg('gpa'))['avg'] or 0 if valid_results.exists() else 0
    
    best_gpa = results.first().gpa if results else 0
    
    division_totals = results.aggregate(
        div1=Sum('division1'),
        div2=Sum('division2'),
        div3=Sum('division3'),
        div4=Sum('division4'),
        div0=Sum('division0')
    )
    
    gpa_ranges = {
        '1_2': results.filter(gpa__gte=1.0, gpa__lt=2.0).count(),
        '2_3': results.filter(gpa__gte=2.0, gpa__lt=3.0).count(),
        '3_4': results.filter(gpa__gte=3.0, gpa__lt=4.0).count(),
        '4_plus': results.filter(gpa__gte=4.0).count(),
    }
    
    # Add ranking position to each result
    ranked_results = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append({
            'rank': rank,
            'school': SchoolSerializer(result.school).data,
            'gpa': result.gpa,
            'division1': result.division1,
            'division2': result.division2,
            'division3': result.division3,
            'division4': result.division4,
            'division0': result.division0,
            'total': result.total,
        })
    
    return Response({
        'results': ranked_results,
        'exam_type': exam_type,
        'year': year,
        'total_schools': total_schools,
        'total_students': total_students,
        'avg_gpa_all': round(avg_gpa_all, 2),
        'best_gpa': round(best_gpa, 4) if best_gpa else 0,
        'division_totals': division_totals,
        'gpa_ranges': gpa_ranges,
    })

@api_view(['GET'])
def home_data(request):
    years = list(ExamResult.objects.values_list('year', flat=True).distinct().order_by('-year'))
    exam_types = sorted(set(ExamResult.objects.values_list('exam', flat=True).distinct()))
    regions = list(School.objects.values_list('region', flat=True).distinct()
                 .exclude(region='Unknown').exclude(region__isnull=True).order_by('region'))
    
    total_schools = School.objects.count()
    top_schools = ExamResult.objects.filter(year=2023, exam='ACSEE').select_related('school').order_by('gpa')[:5]
    
    latest_year = ExamResult.objects.latest('year').year if ExamResult.objects.exists() else None
    
    return Response({
        'years': years,
        'exam_types': exam_types,
        'regions': regions,
        'top_schools': ExamResultSerializer(top_schools, many=True).data,
        'latest_year': latest_year,
        'total_schools': total_schools,
    })

@api_view(['GET'])
def school_detail(request, school_id):
    school = get_object_or_404(School, id=school_id)
    results = ExamResult.objects.filter(school=school).order_by('-year', 'exam')
    
    return Response({
        'school': SchoolSerializer(school).data,
        'results': ExamResultSerializer(results, many=True).data,
    })



from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.management import call_command
from django.core.cache import cache
import threading

@api_view(['POST'])
def trigger_scrape(request):
    """
    Trigger the scraping process via API
    """
    exam_type = request.data.get('exam_type')
    year = request.data.get('year')
    
    if not exam_type or not year:
        return Response({'error': 'exam_type and year are required'}, status=400)
    
    # Check if scraping is already in progress
    if cache.get('scraping_in_progress'):
        return Response({'status': 'scraping_already_in_progress'})
    
    # Run scraping in a separate thread to avoid blocking
    def run_scrape():
        cache.set('scraping_in_progress', True, timeout=3600)  # 1 hour timeout
        try:
            call_command('scrape_necta', exam=exam_type, year=year)
        finally:
            cache.delete('scraping_in_progress')
    
    thread = threading.Thread(target=run_scrape)
    thread.daemon = True
    thread.start()
    
    return Response({'status': 'scraping_started'})

@api_view(['GET'])
def scrape_status(request):
    """
    Check if scraping is in progress
    """
    return Response({
        'scraping_in_progress': bool(cache.get('scraping_in_progress'))
    })