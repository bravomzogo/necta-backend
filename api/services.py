# services.py
from .models import ExamResult

def get_ranked_schools(exam_type: str, year: int):
    """
    Get schools ranked by GPA (lower is better) for a specific exam type and year
    """
    return ExamResult.objects.filter(
        exam=exam_type.upper(), 
        year=year,
        gpa__gt=0  # Exclude schools with invalid GPA
    ).select_related('school').order_by("gpa", "-total") 