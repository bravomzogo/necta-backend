from django.contrib import admin
from .models import School, ExamResult

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "region")
    search_fields = ("code", "name", "region")
    list_filter = ("region",)


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ("school", "exam", "year", "gpa", "total", "division1", "division2", "division3", "division4", "division0")
    search_fields = ("school__name", "school__code", "exam", "year")
    list_filter = ("exam", "year", "school__region")
    ordering = ("gpa", "-total")
