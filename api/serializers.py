from rest_framework import serializers
from .models import School, ExamResult

class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = '__all__'

class ExamResultSerializer(serializers.ModelSerializer):
    school = SchoolSerializer(read_only=True)
    
    class Meta:
        model = ExamResult
        fields = '__all__'