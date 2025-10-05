from django.db import models
from django.contrib.auth.models import User

class CourseSchedule(models.Model):
    teacher_name_course = models.CharField(max_length=100)
    subject_code_course = models.CharField(max_length=20)
    subject_name_course = models.CharField(max_length=100)
    student_group_name_course = models.CharField(max_length=50, blank=True, null=True)
    room_type_course = models.CharField(max_length=50, blank=True, default="")
    section_course = models.CharField(max_length=10)
    theory_slot_amount_course = models.IntegerField(default=0)
    lab_slot_amount_course = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="courses",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("subject_code_course", "section_course", "created_by")  # ✅ สำคัญมาก
        ordering = ["subject_code_course"]

    def __str__(self):
        return f"{self.teacher_name_course} - {self.subject_name_course}"


class PreSchedule(models.Model):
    teacher_name_pre = models.CharField(max_length=100)
    subject_code_pre = models.CharField(max_length=20)
    subject_name_pre = models.CharField(max_length=100)
    student_group_name_pre = models.CharField(max_length=50, blank=True, null=True)
    room_type_pre = models.CharField(max_length=50, blank=True, default="")
    type_pre = models.CharField(max_length=20)
    hours_pre = models.IntegerField(default=0)
    section_pre = models.CharField(max_length=10)
    day_pre = models.CharField(max_length=20, blank=True, default="")
    start_time_pre = models.TimeField()
    stop_time_pre = models.TimeField()
    room_name_pre = models.CharField(max_length=50, blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="preschedules",   # จะใช้ user.preschedules.all()
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.subject_name_pre} - {self.day_pre}"

class WeekActivity(models.Model):
    act_name_activity = models.CharField(max_length=100, blank=True, default="")
    day_activity = models.CharField(max_length=20, blank=True, default="")
    hours_activity = models.IntegerField(default=0)
    start_time_activity = models.TimeField(null=True, blank=True)
    stop_time_activity = models.TimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="week_activities",
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.act_name_activity} - {self.day_activity}"

class ScheduleInfo(models.Model):

    Course_Code = models.CharField(max_length=50)
    Subject_Name = models.CharField(max_length=100, blank=True, default="")
    Teacher = models.CharField(max_length=100, blank=True, default="")
    Room = models.CharField(max_length=50, blank=True, default="")
    Room_Type = models.CharField(max_length=50, blank=True, default="")
    Type = models.CharField(max_length=20, blank=True, default="")
    Curriculum_Type = models.CharField(max_length=20, blank=True, default="")
    Day = models.CharField(max_length=20, blank=True, default="")
    Hour = models.IntegerField(default=0)
    Time_Slot = models.CharField(max_length=20, blank=True, default="")
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="schedules",
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.Course_Code} - {self.Day} {self.Hour:02d}:00"

    class Meta:
        ordering = ["Day", "Hour", "Course_Code"]

class Timedata(models.Model):
    day_of_week = models.CharField(max_length=20)
    start_time = models.CharField(max_length=20)
    stop_time = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.day_of_week}"

class Subject(models.Model):
    code = models.CharField(max_length=20)  # ❌ ลบ unique=True
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="subjects"
    )

    class Meta:
        unique_together = ("code", "created_by")  # ✅ กันซ้ำเฉพาะของ user เดียวกัน
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

class Teacher(models.Model):
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="teachers",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("name", "created_by")   # ✅ ป้องกันชื่อซ้ำ
        ordering = ["name"]

    def __str__(self):
        return self.name

class GroupType(models.Model):
    name = models.CharField(max_length=50)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="group_types",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("name", "created_by")
        ordering = ["name"]

    def __str__(self):
        return self.name

class StudentGroup(models.Model):
    name = models.CharField(max_length=100)
    group_type = models.ForeignKey(
        GroupType, on_delete=models.PROTECT, related_name="student_groups"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="student_groups",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("name", "created_by")
        ordering = ["name"]

    def __str__(self):
        return self.name

# DAY_CHOICES = [
#     ("Mon", "จันทร์"),
#     ("Tue", "อังคาร"),
#     ("Wed", "พุธ"),
#     ("Thu", "พฤหัสบดี"),
#     ("Fri", "ศุกร์"),
#     ("Sat", "เสาร์"),
#     ("Sun", "อาทิตย์"),
# ]

DAY_CHOICES = [
    ("จันทร์", "จันทร์"),
    ("อังคาร", "อังคาร"),
    ("พุธ", "พุธ"),
    ("พฤหัสบดี", "พฤหัสบดี"),
    ("ศุกร์", "ศุกร์"),
    ("เสาร์", "เสาร์"),
    ("อาทิตย์", "อาทิตย์"),
]

class TimeSlot(models.Model):
    day_of_week = models.CharField(max_length=20, choices=DAY_CHOICES)
    start_time = models.TimeField()
    stop_time = models.TimeField()
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="time_slots",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("day_of_week", "start_time", "stop_time", "created_by")
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        return f"{self.day_of_week} {self.start_time}-{self.stop_time}"

class GroupAllow(models.Model):
    group_type = models.ForeignKey(
        GroupType, on_delete=models.CASCADE, related_name="allowed_slots"
    )
    slot = models.ForeignKey(
        TimeSlot, on_delete=models.CASCADE, related_name="group_type_allows"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="group_allows",
        null=True, blank=True
    )
    
    class Meta:
        unique_together = ("group_type", "slot", "created_by")
        ordering = ["group_type__name", "slot__day_of_week", "slot__start_time"]

    def __str__(self):
        return f"{self.group_type} -> {self.slot}"

class RoomType(models.Model):
    name = models.CharField(max_length=50)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ("name", "created_by")
        ordering = ["name"]

    def __str__(self):
        return self.name

class Room(models.Model):
    name = models.CharField(max_length=50)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="rooms",
        null=True, blank=True
    )

    class Meta:
        unique_together = ("name", "created_by")
        ordering = ["name"]

    def __str__(self):
        return self.name

class GeneratedSchedule(models.Model):
    subject_code = models.CharField(max_length=20)
    subject_name = models.CharField(max_length=100)
    teacher = models.CharField(max_length=100, blank=True, null=True)
    student_group = models.CharField(max_length=100, blank=True, null=True)
    section = models.CharField(max_length=10, blank=True, null=True)
    type = models.CharField(max_length=20, blank=True, null=True)  # theory/lab
    hours = models.IntegerField(default=0)

    day_of_week = models.CharField(max_length=20)
    start_time = models.TimeField()
    stop_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="generated_schedules",
        null=True, blank=True
    )

    def __str__(self):
        return f"[GA] {self.subject_code} {self.day_of_week} {self.start_time}-{self.stop_time}"
