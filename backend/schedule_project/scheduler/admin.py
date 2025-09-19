from django.contrib import admin
from .models import (

    CourseSchedule, PreSchedule, WeekActivity, ScheduleInfo, Timedata,

    Subject, Teacher, GroupType, StudentGroup, TimeSlot, GroupAllow,
    RoomType, Room
)

@admin.register(CourseSchedule)
class CourseScheduleAdmin(admin.ModelAdmin):
    list_display  = ['teacher_name_course', 'subject_code_course', 'subject_name_course']
    search_fields = ['teacher_name_course', 'subject_code_course', 'subject_name_course']

@admin.register(WeekActivity)
class WeekActivityAdmin(admin.ModelAdmin):
    list_display = ['act_name_activity', 'day_activity', 'start_time_activity']
    list_filter  = ['day_activity']
    search_fields = ['act_name_activity']

@admin.register(PreSchedule)
class PreScheduleAdmin(admin.ModelAdmin):
    list_display = ['subject_code_pre', 'subject_name_pre', 'teacher_name_pre', 'day_pre', 'start_time_pre', 'stop_time_pre']
    list_filter  = ['day_pre']
    search_fields = ['subject_code_pre', 'subject_name_pre', 'teacher_name_pre']

@admin.register(ScheduleInfo)
class ScheduleInfoAdmin(admin.ModelAdmin):
    list_display = ['Course_Code', 'Subject_Name', 'Teacher', 'Room', 'Day', 'Hour', 'Type']
    list_filter  = ['Day', 'Type']
    search_fields = ['Course_Code', 'Subject_Name', 'Teacher', 'Room']

@admin.register(Timedata)
class TimedataAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'start_time', 'stop_time']
    list_filter  = ['day_of_week']

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(GroupType)
class GroupTypeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'group_type']
    list_filter  = ['group_type']
    search_fields = ['name']

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'start_time', 'stop_time']
    list_filter  = ['day_of_week']
    ordering     = ['day_of_week', 'start_time']

@admin.register(GroupAllow)
class GroupAllowAdmin(admin.ModelAdmin):
    list_display = ['group_type', 'slot']
    list_filter  = ['group_type', 'slot']

@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'room_type']
    list_filter  = ['room_type']
    search_fields = ['name']
