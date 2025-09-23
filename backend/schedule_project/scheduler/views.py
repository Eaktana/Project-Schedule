import csv
import json
import logging
import os
import re
from datetime import datetime, date, time
from io import StringIO
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_time
from django.db import IntegrityError
from django.conf import settings
from django.db.models import Case, When, Value, IntegerField, Q
from django.views.decorators.http import require_GET
from django.db.models import Count

from decimal import Decimal
import math

from .main import run_genetic_algorithm_from_db
from .models import WeekActivity, PreSchedule, CourseSchedule, ScheduleInfo

from .models import (
    GroupAllow,
    GroupType,
    TimeSlot,
    Room,
    RoomType,
    StudentGroup,
    Subject,
    Teacher,
    DAY_CHOICES,
)


logger = logging.getLogger(__name__)


def norm(s: str) -> str:
    return (s or "").strip()


def norm_code(s: str) -> str:
    return norm(s).upper()


def to_int(v, default=0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


DAY_ORDER = Case(
    When(Day__in=["จันทร์", "จ.", "Mon", "MON", "monday"], then=Value(1)),
    When(Day__in=["อังคาร", "อ.", "Tue", "TUE", "tuesday"], then=Value(2)),
    When(Day__in=["พุธ", "พ.", "Wed", "WED", "wednesday"], then=Value(3)),
    When(Day__in=["พฤหัสบดี", "พฤ.", "Thu", "THU", "thursday"], then=Value(4)),
    When(Day__in=["ศุกร์", "ศ.", "Fri", "FRI", "friday"], then=Value(5)),
    When(Day__in=["เสาร์", "ส.", "Sat", "SAT", "saturday"], then=Value(6)),
    When(Day__in=["อาทิตย์", "อา.", "Sun", "SUN", "sunday"], then=Value(7)),
    default=Value(99),
    output_field=IntegerField(),
)


def slot_start_hour(ts: str) -> int:
    m = re.search(r"(\d{1,2})(?::\d{2})?", ts or "")
    return int(m.group(1)) if m else 0


# ========== หน้าเว็บ (Page Views) ==========


def home(request):
    """หน้าแรกของระบบ"""
    context = {
        "title": "ระบบจัดการสอน",
        "total_Course": CourseSchedule.objects.values("teacher_name_course")
        .distinct()
        .count(),
        "total_subjects": CourseSchedule.objects.values("subject_code_course")
        .distinct()
        .count(),
        "total_activity": WeekActivity.objects.count(),
    }
    return render(request, "index.html", context)


def course_page(request):
    from .models import CourseSchedule

    courses = CourseSchedule.objects.all()
    context = {
        "title": "จัดการข้อมูลรายวิชา",
        "courses": courses,
    }
    return render(request, "course.html", context)


def activity_page(request):
    """หน้าจัดการกิจกรรม"""
    activity = WeekActivity.objects.all()
    context = {
        "title": "จัดการกิจกรรม",
        "activity": activity,
    }
    return render(request, "weekactivity.html", context)


def pre_page(request):
    """หน้าจัดการตารางล่วงหน้า"""
    pre_schedules = PreSchedule.objects.all()
    context = {
        "title": "จัดการตารางล่วงหน้า",
        "pre_schedules": pre_schedules,
    }
    return render(request, "pre.html", context)


# Hard-coded slot mapping แทนการใช้ SlotIdSchedule
SLOT_TIME_MAPPING = {
    1: {"start": time(8, 0), "stop": time(9, 0)},
    2: {"start": time(9, 0), "stop": time(10, 0)},
    3: {"start": time(10, 0), "stop": time(11, 0)},
    4: {"start": time(11, 0), "stop": time(12, 0)},
    5: {"start": time(12, 0), "stop": time(13, 0)},
    6: {"start": time(13, 0), "stop": time(14, 0)},
    7: {"start": time(14, 0), "stop": time(15, 0)},
    8: {"start": time(15, 0), "stop": time(16, 0)},
    9: {"start": time(16, 0), "stop": time(17, 0)},
    10: {"start": time(17, 0), "stop": time(18, 0)},
    11: {"start": time(18, 0), "stop": time(19, 0)},
    12: {"start": time(19, 0), "stop": time(20, 0)},
}

# ========== Generate Schedule API ==========
try:
    import numpy as np
except Exception:
    class np:
        integer = ()
        floating = ()
        bool_ = ()

def _san(v):
    # --- แก้ชนิดที่ JSON ไม่รู้จัก ---
    if isinstance(v, (np.integer,)):           # np.int64, np.int32
        return int(v)
    if isinstance(v, (np.floating,)):          # np.float64
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (np.bool_,)):             # np.bool_
        return bool(v)

    if isinstance(v, Decimal):
        return float(v)

    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, (datetime, date)):
        return v.isoformat()

    if isinstance(v, dict):
        return {k: _san(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_san(x) for x in v]

    return v

@csrf_exempt
@require_http_methods(["POST"])
def generate_schedule_api(request):
    try:
        result = run_genetic_algorithm_from_db()
        # ทำความสะอาด payload ทั้งก้อน
        payload = _san(result)
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def create_schedule_csv_file():
    """สร้างไฟล์ CSV จากตารางสอนในฐานข้อมูลและบันทึกลงเซิร์ฟเวอร์"""
    try:

        schedules = ScheduleInfo.objects.order_by("id")

        if not schedules.exists():
            return {"status": "error", "message": "ไม่พบตารางสอนในระบบ"}

        # สร้างชื่อไฟล์ที่มี timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"schedule_{timestamp}.csv"

        # สร้างโฟลเดอร์ media/schedules หากยังไม่มี
        media_root = getattr(settings, "MEDIA_ROOT", "media")
        schedule_dir = os.path.join(media_root, "schedules")
        os.makedirs(schedule_dir, exist_ok=True)

        # เส้นทางไฟล์เต็ม
        file_path = os.path.join(schedule_dir, filename)

        # เขียนไฟล์ CSV
        with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)

            # เขียน header
            writer.writerow(
                ["รหัสวิชา", "ชื่อวิชา", "อาจารย์", "ห้อง", "ประเภท", "วัน", "ชั่วโมง"]
            )

            # เขียนข้อมูล
            for schedule in schedules:
                writer.writerow(
                    [
                        schedule.Course_Code,
                        schedule.Subject_Name,
                        schedule.Teacher,
                        schedule.Room,
                        schedule.Type,
                        schedule.Day,
                        schedule.Hour,
                    ]
                )

        return {
            "status": "success",
            "message": f"สร้างไฟล์ CSV สำเร็จ: {filename}",
            "file_path": filename,
            "full_path": file_path,
            "total_records": schedules.count(),
        }

    except Exception as e:
        logger.error(f"Error creating CSV file: {e}")
        return {"status": "error", "message": f"เกิดข้อผิดพลาดในการสร้างไฟล์ CSV: {str(e)}"}


# ========== Test Program API ==========


@csrf_exempt
@require_http_methods(["POST"])
def test_program_api(request):
    """API สำหรับทดสอบโปรแกรม"""
    try:
        course_count = CourseSchedule.objects.count()
        return JsonResponse(
            {
                "status": "success",
                "message": "ระบบทำงานปกติ",
                "data": {
                    "courses": course_count,
                    "timestamp": datetime.now().isoformat(),
                },
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Test program error: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["GET"])
def view_schedule_api(request):
    from .models import ScheduleInfo  # ปรับให้ตรง app ของคุณ

    order = (request.GET.get("order") or "id").lower().strip()
    direction = (request.GET.get("dir") or "asc").lower().strip()

    def with_dir(*fields):
        return [f if direction == "asc" else f"-{f}" for f in fields]

    qs = ScheduleInfo.objects.all()

    if order == "day":
        qs = qs.annotate(day_order=DAY_ORDER).order_by(
            *with_dir("day_order", "Hour", "Course_Code", "id")
        )
    elif order == "hour":
        qs = qs.annotate(day_order=DAY_ORDER).order_by(
            *with_dir("day_order", "Hour", "id")
        )
    elif order == "course":
        qs = qs.order_by(*with_dir("Course_Code", "id"))
    else:
        qs = qs.order_by(*with_dir("id"))

    schedules = []
    for s in qs:
        hour = s.Hour or slot_start_hour(getattr(s, "Time_Slot", ""))
        schedules.append(
            {
                "id": s.id,
                "Course_Code": getattr(s, "Course_Code", "")
                or getattr(s, "Course", ""),
                "Subject_Name": getattr(s, "Subject_Name", "")
                or getattr(s, "Course_Name", ""),
                "Teacher": getattr(s, "Teacher", "") or "",
                "Room": getattr(s, "Room", "") or "",
                "Room_Type": getattr(s, "Room_Type", "") or "",
                "Type": getattr(s, "Type", "") or "",
                "Day": getattr(s, "Day", "") or "",
                "Hour": hour,
                "Time_Slot": getattr(s, "Time_Slot", "") or "",
                # ถ้ามีฟิลด์กลุ่มนักศึกษา/section ให้ส่งด้วย (ไม่มีได้ค่าว่าง)
                "Student_Group": getattr(s, "Student_Group", "")
                or getattr(s, "Section", "")
                or "",
            }
        )

    return JsonResponse(
        {"status": "success", "total_entries": len(schedules), "schedules": schedules},
        json_dumps_params={"ensure_ascii": False},
    )

# ===== View from GeneratedSchedule (สำหรับหน้าเลือก) =====


@csrf_exempt
@require_http_methods(["GET"])
def view_generated_schedule_api(request):
    from .models import GeneratedSchedule

    qs = GeneratedSchedule.objects.all().order_by("day_of_week", "start_time", "id")

    schedules = []
    for g in qs:
        schedules.append({
            
            "Course_Code": g.subject_code or "",
            "Subject_Name": g.subject_name or "",
            "Teacher": g.teacher or "",
            "Room": g.room or "",
            "Type": g.type or "",
            "Student_Group": g.student_group or "",
            "Day": g.day_of_week or "",
            "StartTime": g.start_time.strftime("%H:%M") if g.start_time else "",
            "StopTime": g.stop_time.strftime("%H:%M") if g.stop_time else "",
            # เผื่อโค้ดเดิมยังอิง Hour
            "Hour": int(g.start_time.strftime("%H")) if g.start_time else None,
        })

    return JsonResponse(
        {"status": "success", "total_entries": len(schedules), "schedules": schedules},
        json_dumps_params={"ensure_ascii": False},
    )

# ========== Clear Schedule API ==========


@csrf_exempt
@require_http_methods(["POST"])
def clear_schedule_api(request):
    """API สำหรับลบตารางสอนทั้งหมดในฐานข้อมูล"""
    try:
        deleted_count = ScheduleInfo.objects.count()
        ScheduleInfo.objects.all().delete()

        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบตารางสอนทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error clearing schedule: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบตารางสอน: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def delete_selected_schedules_api(request):
    """API สำหรับลบตารางสอนที่เลือกในฐานข้อมูล"""
    try:

        data = json.loads(request.body)
        schedule_ids = data.get("schedule_ids", [])

        if not schedule_ids:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบรายการที่ต้องการลบ"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # Convert string IDs to integers
        try:
            schedule_ids = [int(id) for id in schedule_ids]
        except ValueError:
            return JsonResponse(
                {"status": "error", "message": "รูปแบบ ID ไม่ถูกต้อง"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # Delete selected schedules
        deleted_count, _ = ScheduleInfo.objects.filter(id__in=schedule_ids).delete()

        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบรายการที่เลือกสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "รูปแบบข้อมูลไม่ถูกต้อง"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting selected schedules: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบรายการที่เลือก: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


# ========== COURSE APIs ==========


@csrf_exempt
def get_courses(request):
    """API สำหรับดึงข้อมูลรายวิชาทั้งหมด"""
    try:
        qs = CourseSchedule.objects.all()
        items = []
        for c in qs:
            items.append(
                {
                    "id": c.id,
                    "teacher_name_course": c.teacher_name_course,
                    "subject_code_course": c.subject_code_course,
                    "subject_name_course": c.subject_name_course,
                    "student_group_name_course": c.student_group_name_course,
                    "room_type_course": c.room_type_course,
                    "section_course": c.section_course,
                    "theory_slot_amount_course": c.theory_slot_amount_course,
                    "lab_slot_amount_course": c.lab_slot_amount_course,
                }
            )
        return JsonResponse(
            {"status": "success", "courses": items},
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error getting course: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


def _teacher_name_from_id(raw):
    try:
        tid = int(raw)
    except (TypeError, ValueError):
        return ""
    t = Teacher.objects.filter(id=tid).only("name").first()
    return t.name if t else ""


@csrf_exempt
@require_http_methods(["POST"])
def add_course(request):
    """API สำหรับเพิ่มรายวิชา (กันซ้ำ: วิชาเดียวกัน + sec เดียวกัน)"""
    try:
        data = json.loads(request.body or "{}")

        code = norm_code(data.get("subject_code") or data.get("subject_code_course"))
        section = (data.get("section") or data.get("section_course") or "").strip()

        if not code:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุรหัสวิชา"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )
        if not section:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุกลุ่มเรียน (เช่น sec1)"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # กันซ้ำระดับแอป
        if CourseSchedule.objects.filter(
            subject_code_course=code, section_course=section
        ).exists():
            return JsonResponse(
                {"status": "error", "message": f"วิชา {code} กลุ่ม {section} มีอยู่แล้ว"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        teacher_name = (
            _teacher_name_from_id(data.get("teacher_id"))
            or data.get("teacher_name")
            or data.get("teacher_name_course")
        )

        course = CourseSchedule.objects.create(
            teacher_name_course=teacher_name,
            subject_code_course=code,
            subject_name_course=(
                data.get("subject_name") or data.get("subject_name_course")
            ),
            student_group_name_course=(
                data.get("student_group_id")
                or data.get("student_group_name_course")
                or ""
            ),
            room_type_course=(
                data.get("room_type") or data.get("room_type_course") or ""
            ),
            section_course=section,
            theory_slot_amount_course=to_int(
                data.get("theory_hours") or data.get("theory_slot_amount_course"), 0
            ),
            lab_slot_amount_course=to_int(
                data.get("lab_hours") or data.get("lab_slot_amount_course"), 0
            ),
        )

        return JsonResponse(
            {
                "status": "success",
                "message": "เพิ่มข้อมูลรายวิชาสำเร็จ",
                "course_id": course.id,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error adding course: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def add_course_bulk(request):
    """API สำหรับเพิ่มรายวิชาหลายรายการพร้อมกัน"""
    try:
        data = json.loads(request.body)
        rows = data.get("courses", data.get("course", []))

        created_ids = []

        for row in rows:

            def g(key_simple, key_old):
                return row.get(key_simple, row.get(key_old))

            teacher_name = (
                _teacher_name_from_id(row.get("teacher_id"))
                or row.get("teacher_name")
                or row.get("teacher_name_course")
            )

            c = CourseSchedule.objects.create(
                teacher_name_course=teacher_name,
                subject_code_course=norm_code(g("subject_code", "subject_code_course")),
                subject_name_course=g("subject_name", "subject_name_course"),
                student_group_name_course=g(
                    "student_group_id", "student_group_name_course"
                )
                or "",
                room_type_course=g("room_type", "room_type_course") or "",
                section_course=g("section", "section_course"),
                theory_slot_amount_course=to_int(
                    g("theory_hours", "theory_slot_amount_course"), 0
                ),
                lab_slot_amount_course=to_int(
                    g("lab_hours", "lab_slot_amount_course"), 0
                ),
            )
            created_ids.append(c.id)

        return JsonResponse(
            {
                "status": "success",
                "message": f"เพิ่มรายวิชา {len(created_ids)} รายการสำเร็จ",
                "created_ids": created_ids,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error adding course bulk: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["PUT"])
def update_course(request, id):
    """API สำหรับแก้ไขรายวิชา (กันซ้ำ: วิชาเดียวกัน + sec เดียวกัน โดยยกเว้นแถวตัวเอง)"""
    try:
        course = CourseSchedule.objects.get(id=id)
        data = json.loads(request.body or "{}")

        new_code = norm_code(
            data.get("subject_code")
            or data.get("subject_code_course")
            or course.subject_code_course
        )
        new_section = (
            data.get("section") or data.get("section_course") or course.section_course
        ).strip()

        if not new_code:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุรหัสวิชา"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )
        if not new_section:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุกลุ่มเรียน (เช่น sec1)"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # กันซ้ำโดย exclude ตัวเอง
        if (
            CourseSchedule.objects.filter(
                subject_code_course=new_code, section_course=new_section
            )
            .exclude(id=id)
            .exists()
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"วิชา {new_code} กลุ่ม {new_section} มีอยู่แล้ว",
                },
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # อัปเดตฟิลด์
        course.teacher_name_course = (
            _teacher_name_from_id(data.get("teacher_id"))
            or data.get("teacher_name")
            or data.get("teacher_name_course")
            or course.teacher_name_course
        )
        course.subject_code_course = new_code
        course.subject_name_course = (
            data.get("subject_name")
            or data.get("subject_name_course")
            or course.subject_name_course
        )
        course.student_group_name_course = (
            data.get("student_group_id")
            or data.get("student_group_name_course")
            or course.student_group_name_course
        )
        course.room_type_course = (
            data.get("room_type")
            or data.get("room_type_course")
            or course.room_type_course
        )
        course.section_course = new_section
        course.theory_slot_amount_course = to_int(
            data.get("theory_hours")
            or data.get("theory_slot_amount_course")
            or course.theory_slot_amount_course,
            course.theory_slot_amount_course,
        )
        course.lab_slot_amount_course = to_int(
            data.get("lab_hours")
            or data.get("lab_slot_amount_course")
            or course.lab_slot_amount_course,
            course.lab_slot_amount_course,
        )

        course.save()

        return JsonResponse(
            {"status": "success", "message": "แก้ไขข้อมูลรายวิชาสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )

    except CourseSchedule.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบรายวิชาที่ต้องการแก้ไข"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error updating course: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_course(request, id):
    """API สำหรับลบข้อมูลรายวิชา"""
    try:
        course = CourseSchedule.objects.get(id=id)
        course.delete()

        return JsonResponse(
            {"status": "success", "message": "ลบข้อมูลรายวิชาสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )
    except CourseSchedule.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลรายวิชา"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting course: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def upload_course_csv(request):
    """API สำหรับอัปโหลดไฟล์ CSV ข้อมูลรายวิชา"""
    try:
        if "file" not in request.FILES:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบไฟล์ที่อัปโหลด"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        csv_file = request.FILES["file"]

        if not csv_file.name.endswith(".csv"):
            return JsonResponse(
                {"status": "error", "message": "กรุณาอัปโหลดไฟล์ CSV เท่านั้น"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # อ่านไฟล์ CSV พร้อมจัดการ encoding
        try:
            decoded_file = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            for enc in ("utf-8", "cp874", "tis-620", "cp1252"):
                try:
                    csv_file.seek(0)
                    decoded_file = csv_file.read().decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

        csv_data = StringIO(decoded_file)
        reader = csv.DictReader(csv_data)

        created_count = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                CourseSchedule.objects.create(
                    teacher_name_course=norm(
                        row.get("teacher_name") or row.get("teacher_name_course") or ""
                    ),
                    subject_code_course=norm_code(
                        row.get("subject_code") or row.get("subject_code_course") or ""
                    ),
                    subject_name_course=norm(
                        row.get("subject_name") or row.get("subject_name_course") or ""
                    ),
                    student_group_name_course=norm(
                        row.get("student_group_id")
                        or row.get("student_group_name_course")
                        or ""
                    ),
                    room_type_course=norm(
                        row.get("room_type") or row.get("room_type_course") or ""
                    ),
                    section_course=norm(
                        row.get("section") or row.get("section_course") or ""
                    ),
                    theory_slot_amount_course=to_int(
                        row.get("theory_hours")
                        or row.get("theory_slot_amount_course")
                        or 0
                    ),
                    lab_slot_amount_course=to_int(
                        row.get("lab_hours") or row.get("lab_slot_amount_course") or 0
                    ),
                )
                created_count += 1
            except Exception as e:
                errors.append(f"แถว {row_num}: {str(e)}")

        if errors:
            return JsonResponse(
                {
                    "status": "partial_success",
                    "message": f"อัปโหลดสำเร็จ {created_count} รายการ แต่มีข้อผิดพลาด {len(errors)} รายการ",
                    "created_count": created_count,
                    "errors": errors[:10],  # แสดงแค่ 10 ข้อผิดพลาดแรก
                },
                json_dumps_params={"ensure_ascii": False},
            )

        return JsonResponse(
            {
                "status": "success",
                "message": f"อัปโหลดข้อมูลรายวิชาสำเร็จ {created_count} รายการ",
                "created_count": created_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error uploading course CSV: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["DELETE"])
def course_delete_all(request):
    """API สำหรับลบรายวิชาทั้งหมด"""
    try:
        from .models import CourseSchedule
        deleted_count, _ = CourseSchedule.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ Course ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})



# ========== PRE-SCHEDULE APIs ==========


@csrf_exempt
def get_pre(request):
    """API สำหรับดึงข้อมูลตารางล่วงหน้าทั้งหมด"""
    try:
        pre_schedules = PreSchedule.objects.all()
        pre_data = []

        for pre in pre_schedules:
            pre_data.append(
                {
                    "id": pre.id,
                    "teacher_name_pre": pre.teacher_name_pre,
                    "subject_code_pre": pre.subject_code_pre,
                    "subject_name_pre": pre.subject_name_pre,
                    "student_group_name_pre": pre.student_group_name_pre,
                    "room_type_pre": pre.room_type_pre,
                    "type_pre": pre.type_pre,
                    "hours_pre": pre.hours_pre,
                    "section_pre": pre.section_pre,
                    "day_pre": pre.day_pre,
                    "start_time_pre": (
                        pre.start_time_pre.strftime("%H:%M")
                        if pre.start_time_pre
                        else ""
                    ),
                    "stop_time_pre": (
                        pre.stop_time_pre.strftime("%H:%M") if pre.stop_time_pre else ""
                    ),
                    "room_name_pre": pre.room_name_pre,
                }
            )

        return JsonResponse(
            {"status": "success", "pre_schedules": pre_data},
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error getting pre schedules: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
# ------------- new add ตรวจสอบใช้ห้องซ้ำกัน-----------------------------------------------
def add_pre(request):
    """API สำหรับเพิ่มตารางล่วงหน้า (กันชนเวลา + กันซ้ำ วิชา/เซกชัน/ภาคทฤษฎี-ปฏิบัติ[room_type_pre])"""
    try:
        data = json.loads(request.body or "{}")

        # --- normalize รหัสวิชา ---
        code = norm_code(data.get("subject_code_pre", ""))
        if not code:
            return JsonResponse(
                {"status": "error", "message": "รหัสวิชาห้ามว่าง"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # ===== ค่าประเภทต่าง ๆ =====
        # ภาคทฤษฎี/ปฏิบัติ -> room_type_pre (ใช้กันซ้ำ)
        phase_val = (
            data.get("room_type_pre") or data.get("subject_type_pre") or ""
        ).strip()
        # ประเภทรายวิชา/ประเภทห้อง -> type_pre (ไม่ใช้กันซ้ำ)
        type_val = (
            data.get("type_pre") or data.get("subject_room_type_pre") or ""
        ).strip()

        # --- เวลาเริ่ม/สิ้นสุด ---
        start_time = parse_time_flexible(data.get("start_time_pre"), "08:00")
        if data.get("stop_time_pre"):
            stop_time = parse_time_flexible(data.get("stop_time_pre"), "09:00")
        else:
            stop_s = compute_stop_str(
                data.get("start_time_pre", ""), str(data.get("hours_pre", "0"))
            )
            stop_time = parse_time_flexible(stop_s or "09:00", "09:00")

        # --- ตรวจสอบเวลาเบื้องต้น ---
        if not start_time or not stop_time:
            return JsonResponse(
                {"status": "error", "message": "รูปแบบเวลาไม่ถูกต้อง"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )
        if start_time >= stop_time:
            return JsonResponse(
                {"status": "error", "message": "เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # --- กันซ้ำ: วิชา + กลุ่มเรียน + ภาค(ทฤษฎี/ปฏิบัติ=room_type_pre) ---
        section_val = (data.get("section_pre") or "").strip()
        if code and section_val:
            dup_exists = PreSchedule.objects.filter(
                subject_code_pre=code,
                section_pre=section_val,
                room_type_pre=phase_val,  # ← ใช้ room_type_pre เป็นตัวแยกภาค
            ).exists()
            if dup_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"วิชา {code} กลุ่ม {section_val} ({phase_val or 'ไม่ระบุภาค'}) มีอยู่แล้ว",
                    },
                    status=400,
                    json_dumps_params={"ensure_ascii": False},
                )

        # --- กันชนเวลาห้องเดียวกัน/วันเดียวกัน ---
        room_name = (data.get("room_name_pre") or "").strip()
        day = (data.get("day_pre") or "").strip()
        if room_name and day:
            overlap_exists = (
                PreSchedule.objects.filter(
                    room_name_pre=room_name,
                    day_pre=day,
                )
                .filter(
                    Q(start_time_pre__lt=stop_time) & Q(stop_time_pre__gt=start_time)
                )
                .exists()
            )
            if overlap_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"เวลาซ้ำกับรายการอื่นในห้อง {room_name} วัน {day} "
                            f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}"
                        ),
                    },
                    status=400,
                    json_dumps_params={"ensure_ascii": False},
                )

        # --- ผ่านแล้ว -> บันทึก ---
        pre = PreSchedule.objects.create(
            teacher_name_pre=data.get("teacher_name_pre"),
            subject_code_pre=code,
            subject_name_pre=data.get("subject_name_pre"),
            student_group_name_pre=data.get("student_group_name_pre", ""),
            room_type_pre=phase_val,  # ภาคทฤษฎี/ปฏิบัติ
            type_pre=type_val,  # ประเภทรายวิชา/ประเภทห้อง
            hours_pre=to_int(data.get("hours_pre", 0)),
            section_pre=section_val,
            day_pre=day,
            start_time_pre=start_time,
            stop_time_pre=stop_time,
            room_name_pre=room_name,
        )

        return JsonResponse(
            {"status": "success", "message": "เพิ่มตารางล่วงหน้าสำเร็จ", "pre_id": pre.id},
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error adding pre schedule: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["DELETE"])
def pre_delete_all(request):
    """API สำหรับลบ PreSchedule ทั้งหมด"""
    try:
        deleted_count, _ = PreSchedule.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ PreSchedule ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})

# add_pre เดิม ===============================================
# def add_pre(request):
#     """API สำหรับเพิ่มตารางล่วงหน้า"""
#     try:
#         data = json.loads(request.body)

#         code = norm_code(data.get("subject_code_pre", ""))
#         if not code:
#             return JsonResponse(
#                 {"status": "error", "message": "รหัสวิชาห้ามว่าง"},
#                 status=400,
#                 json_dumps_params={"ensure_ascii": False},
#             )

#         # แปลง/เตรียมเวลาเริ่ม
#         start_time = parse_time_flexible(data.get("start_time_pre"), "08:00")

#         # ถ้าฝั่งหน้าเว็บไม่ส่ง stop_time_pre มา ให้คำนวณจาก start + hours
#         if data.get("stop_time_pre"):
#             stop_time = parse_time_flexible(data.get("stop_time_pre"), "09:00")
#         else:
#             stop_s = compute_stop_str(
#                 data.get("start_time_pre", ""), str(data.get("hours_pre", "0"))
#             )
#             stop_time = parse_time_flexible(stop_s or "09:00", "09:00")

#         pre = PreSchedule.objects.create(
#             teacher_name_pre=data.get("teacher_name_pre"),
#             subject_code_pre=code,  # using normalized code
#             subject_name_pre=data.get("subject_name_pre"),
#             student_group_name_pre=data.get("student_group_name_pre", ""),
#             room_type_pre=data.get("room_type_pre", ""),
#             type_pre=data.get("type_pre", ""),
#             hours_pre=to_int(data.get("hours_pre", 0)),
#             section_pre=data.get("section_pre"),
#             day_pre=data.get("day_pre", ""),
#             start_time_pre=start_time,
#             stop_time_pre=stop_time,
#             room_name_pre=data.get("room_name_pre", ""),
#         )

#         return JsonResponse(
#             {"status": "success", "message": "เพิ่มตารางล่วงหน้าสำเร็จ", "pre_id": pre.id},
#             json_dumps_params={"ensure_ascii": False},
#         )
#     except Exception as e:
#         logger.error(f"Error adding pre schedule: {e}")
#         return JsonResponse(
#             {"status": "error", "message": str(e)},
#             status=500,
#             json_dumps_params={"ensure_ascii": False},
#         )


@csrf_exempt
@require_http_methods(["PUT"])
# ------------- new update ตรวจสอบใช้ห้องซ้ำกัน-----------------------------------------------
def update_pre(request, id):
    """API สำหรับแก้ไขตารางล่วงหน้า (กันชนเวลา + กันซ้ำ วิชา/กลุ่ม/ภาคทฤษฎี-ปฏิบัติ[room_type_pre])"""
    try:
        pre = PreSchedule.objects.get(id=id)
        data = json.loads(request.body or "{}")

        # ---- ฟิลด์รหัสวิชา (normalize) ----
        code_in = (
            norm_code(data.get("subject_code_pre", pre.subject_code_pre))
            or pre.subject_code_pre
        )

        # ---- ฟิลด์ทั่วไป ----
        teacher_name = data.get("teacher_name_pre", pre.teacher_name_pre)
        subject_name = data.get("subject_name_pre", pre.subject_name_pre)
        group_name = data.get("student_group_name_pre", pre.student_group_name_pre)

        # ภาคทฤษฎี/ปฏิบัติ -> room_type_pre (ใช้กันซ้ำ)
        phase_val = (
            data.get("room_type_pre", pre.room_type_pre)
            or data.get("subject_type_pre", pre.room_type_pre)
            or ""
        ).strip()
        # ประเภทรายวิชา/ประเภทห้อง -> type_pre (ไม่ใช้กันซ้ำ)
        type_val = (
            data.get("type_pre", pre.type_pre)
            or data.get("subject_room_type_pre", pre.type_pre)
            or ""
        ).strip()

        hours_val = to_int(data.get("hours_pre", pre.hours_pre))
        section_val = (data.get("section_pre", pre.section_pre) or "").strip()
        day_val = (data.get("day_pre", pre.day_pre) or "").strip()
        room_name_val = (data.get("room_name_pre", pre.room_name_pre) or "").strip()

        # ---- เวลาเริ่ม/สิ้นสุด ----
        start_in = data.get("start_time_pre")
        stop_in = data.get("stop_time_pre")

        start_time = parse_time_flexible(
            (
                start_in
                if start_in
                else (
                    pre.start_time_pre.strftime("%H:%M") if pre.start_time_pre else None
                )
            ),
            pre.start_time_pre.strftime("%H:%M") if pre.start_time_pre else "08:00",
        )

        if stop_in:
            stop_time = parse_time_flexible(
                stop_in,
                pre.stop_time_pre.strftime("%H:%M") if pre.stop_time_pre else "09:00",
            )
        else:
            start_for_calc = start_in or (
                pre.start_time_pre.strftime("%H:%M") if pre.start_time_pre else ""
            )
            hours_for_calc = data.get("hours_pre", pre.hours_pre)
            stop_str = compute_stop_str(start_for_calc, str(hours_for_calc))
            stop_time = parse_time_flexible(
                stop_str
                or (
                    pre.stop_time_pre.strftime("%H:%M")
                    if pre.stop_time_pre
                    else "09:00"
                ),
                "09:00",
            )

        # ---- ตรวจรูปแบบเวลา ----
        if not start_time or not stop_time:
            return JsonResponse(
                {"status": "error", "message": "รูปแบบเวลาไม่ถูกต้อง"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )
        if start_time >= stop_time:
            return JsonResponse(
                {"status": "error", "message": "เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # ---- กันซ้ำ: รหัสวิชา + กลุ่มเรียน + ภาค(ทฤษฎี/ปฏิบัติ=room_type_pre) (ยกเว้นตัวเอง) ----
        if code_in and section_val:
            dup_exists = (
                PreSchedule.objects.filter(
                    subject_code_pre=code_in,
                    section_pre=section_val,
                    room_type_pre=phase_val,  # ← ใช้ room_type_pre เป็นตัวแยกภาค
                )
                .exclude(id=id)
                .exists()
            )
            if dup_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"วิชา {code_in} กลุ่ม {section_val} ({phase_val or 'ไม่ระบุภาค'}) มีอยู่แล้ว",
                    },
                    status=400,
                    json_dumps_params={"ensure_ascii": False},
                )

        # ---- กันชนเวลาห้องเดียวกัน/วันเดียวกัน (ยกเว้นตัวเอง) ----
        if room_name_val and day_val:
            conflict = (
                PreSchedule.objects.filter(room_name_pre=room_name_val, day_pre=day_val)
                .exclude(id=id)
                .filter(
                    Q(start_time_pre__lt=stop_time) & Q(stop_time_pre__gt=start_time)
                )
                .exists()
            )

            if conflict:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"เวลาซ้ำกับรายการอื่นในห้อง {room_name_val} วัน {day_val} "
                            f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}"
                        ),
                    },
                    status=400,
                    json_dumps_params={"ensure_ascii": False},
                )

        # ---- ผ่านแล้ว: อัปเดตและบันทึก ----
        pre.teacher_name_pre = teacher_name
        pre.subject_code_pre = code_in
        pre.subject_name_pre = subject_name
        pre.student_group_name_pre = group_name
        pre.room_type_pre = phase_val  # ภาคทฤษฎี/ปฏิบัติ
        pre.type_pre = type_val  # ประเภทรายวิชา/ประเภทห้อง
        pre.hours_pre = hours_val
        pre.section_pre = section_val
        pre.day_pre = day_val
        pre.start_time_pre = start_time
        pre.stop_time_pre = stop_time
        pre.room_name_pre = room_name_val
        pre.save()

        return JsonResponse(
            {"status": "success", "message": "แก้ไขตารางล่วงหน้าสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )

    except PreSchedule.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลตารางล่วงหน้า"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error updating pre schedule: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


# update เดิม ===================================================
# def update_pre(request, id):
#     """API สำหรับแก้ไขตารางล่วงหน้า"""
#     try:
#         pre = PreSchedule.objects.get(id=id)
#         data = json.loads(request.body)

#         code_in = norm_code(data.get("subject_code_pre", pre.subject_code_pre))
#         if not code_in:
#             pre.subject_code_pre = code_in
#             # กำลังให้ดูจากเดิม -> มีแค่
#             # ถ้าว่าง ให้ดูจากเดิม

#         # ฟิลด์ทั่วไป
#         pre.teacher_name_pre = data.get("teacher_name_pre", pre.teacher_name_pre)
#         pre.subject_code_pre = code_in  # using normalized code
#         pre.subject_name_pre = data.get("subject_name_pre", pre.subject_name_pre)
#         pre.student_group_name_pre = data.get(
#             "student_group_name_pre", pre.student_group_name_pre
#         )
#         pre.room_type_pre = data.get("room_type_pre", pre.room_type_pre)
#         pre.type_pre = data.get("type_pre", pre.type_pre)
#         pre.hours_pre = to_int(data.get("hours_pre", pre.hours_pre))
#         pre.section_pre = data.get("section_pre", pre.section_pre)
#         pre.day_pre = data.get("day_pre", pre.day_pre)
#         pre.room_name_pre = data.get("room_name_pre", pre.room_name_pre)

#         # จัดการเวลา
#         start_in = data.get("start_time_pre")
#         stop_in = data.get("stop_time_pre")

#         if start_in:
#             pre.start_time_pre = parse_time_flexible(start_in, "08:00")

#         if stop_in:
#             # ถ้าส่ง stop มา ใช้ค่าที่ส่งมา
#             pre.stop_time_pre = parse_time_flexible(stop_in, "09:00")
#         else:
#             # ไม่ส่ง stop มา -> คำนวณจาก start + hours (ใช้ค่าที่ส่งใหม่หรือของเดิม)
#             start_for_calc = start_in or (
#                 pre.start_time_pre.strftime("%H:%M") if pre.start_time_pre else ""
#             )
#             hours_for_calc = data.get("hours_pre", pre.hours_pre)
#             stop_str = compute_stop_str(start_for_calc, str(hours_for_calc))
#             if stop_str:
#                 pre.stop_time_pre = parse_time_flexible(stop_str, "09:00")

#         pre.save()
#         return JsonResponse(
#             {"status": "success", "message": "แก้ไขตารางล่วงหน้าสำเร็จ"},
#             json_dumps_params={"ensure_ascii": False},
#         )

#     except PreSchedule.DoesNotExist:
#         return JsonResponse(
#             {"status": "error", "message": "ไม่พบข้อมูลตารางล่วงหน้า"},
#             status=404,
#             json_dumps_params={"ensure_ascii": False},
#         )

#     except Exception as e:
#         logger.error(f"Error updating pre schedule: {e}")
#         return JsonResponse(
#             {"status": "error", "message": str(e)},
#             status=500,
#             json_dumps_params={"ensure_ascii": False},
#         )


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_pre(request, id):
    """API สำหรับลบตารางล่วงหน้า"""
    try:
        pre = PreSchedule.objects.get(id=id)
        pre.delete()

        return JsonResponse(
            {"status": "success", "message": "ลบตารางล่วงหน้าสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )
    except PreSchedule.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลตารางล่วงหน้า"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting pre schedule: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def upload_pre_csv(request):
    """API สำหรับอัปโหลดไฟล์ CSV ตารางล่วงหน้า"""
    try:
        if "file" not in request.FILES:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบไฟล์ที่อัปโหลด"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        csv_file = request.FILES["file"]

        if not csv_file.name.endswith(".csv"):
            return JsonResponse(
                {"status": "error", "message": "กรุณาอัปโหลดไฟล์ CSV เท่านั้น"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # อ่านไฟล์ CSV พร้อมจัดการ encoding
        try:
            decoded_file = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            for enc in ("utf-8", "cp874", "tis-620", "cp1252"):
                try:
                    csv_file.seek(0)
                    decoded_file = csv_file.read().decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

        csv_data = StringIO(decoded_file)
        reader = csv.DictReader(csv_data)

        created_count = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:

                start_str = (row.get("start_time_pre", "") or "").strip()
                hours_str = (row.get("hours_pre", "") or "").strip()
                stop_str = (row.get("stop_time_pre", "") or "").strip()
                if not stop_str:
                    stop_str = compute_stop_str(
                        start_str, hours_str
                    )  # ใช้ยูทิลิตี้คำนวณของคุณ
                start_val = parse_time_flexible(start_str, "08:00")
                stop_val = parse_time_flexible(stop_str or "09:00", "09:00")

                PreSchedule.objects.create(
                    teacher_name_pre=norm(row.get("teacher_name_pre", "")),
                    subject_code_pre=norm_code(row.get("subject_code_pre", "")),
                    subject_name_pre=norm(row.get("subject_name_pre", "")),
                    student_group_name_pre=norm(row.get("student_group_name_pre", "")),
                    room_type_pre=norm(row.get("room_type_pre", "")),
                    type_pre=norm(row.get("type_pre", "")),
                    hours_pre=to_int(hours_str),
                    day_pre=norm(row.get("day_pre", "")),
                    start_time_pre=start_val,
                    stop_time_pre=stop_val,
                    room_name_pre=norm_code(row.get("room_name_pre", "")),
                )

                created_count += 1
            except Exception as e:
                errors.append(f"แถว {row_num}: {str(e)}")

        if errors:
            return JsonResponse(
                {
                    "status": "partial_success",
                    "message": f"อัปโหลดสำเร็จ {created_count} รายการ แต่มีข้อผิดพลาด {len(errors)} รายการ",
                    "created_count": created_count,
                    "errors": errors[:10],
                },
                json_dumps_params={"ensure_ascii": False},
            )

        return JsonResponse(
            {
                "status": "success",
                "message": f"อัปโหลดตารางล่วงหน้าสำเร็จ {created_count} รายการ",
                "created_count": created_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error uploading pre CSV: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


# ========== ACTIVITY APIs ==========

@csrf_exempt
@require_http_methods(["DELETE"])
def activity_delete_all(request):
    """API สำหรับลบ WeekActivity ทั้งหมด"""
    try:
        deleted_count, _ = WeekActivity.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ Activity ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def get_activity(request):
    """API สำหรับดึงข้อมูลกิจกรรมทั้งหมด"""
    try:
        activity = WeekActivity.objects.all()
        activity_data = []

        for activity in activity:
            activity_data.append(
                {
                    "id": activity.id,
                    "act_name_activity": activity.act_name_activity,
                    "day_activity": activity.day_activity,
                    "start_time_activity": (
                        activity.start_time_activity.strftime("%H:%M")
                        if activity.start_time_activity
                        else ""
                    ),
                    "stop_time_activity": (
                        activity.stop_time_activity.strftime("%H:%M")
                        if activity.stop_time_activity
                        else ""
                    ),
                }
            )

        return JsonResponse(
            {"status": "success", "activity": activity_data},
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def add_activity(request):
    """API สำหรับเพิ่มกิจกรรม"""
    try:
        data = json.loads(request.body)

        # แปลงเวลาจาก string เป็น time object
        start_time = parse_time_flexible(data.get("start_time_activity"), "08:00")
        stop_time = parse_time_flexible(data.get("stop_time_activity"), "09:00")

        activity = WeekActivity.objects.create(
            act_name_activity=data.get("act_name_activity"),
            day_activity=data.get("day_activity", ""),
            hours_activity=int(data.get("hours_activity", 0)),
            start_time_activity=start_time,
            stop_time_activity=stop_time,
        )

        return JsonResponse(
            {
                "status": "success",
                "message": "เพิ่มกิจกรรมสำเร็จ",
                "activity_id": activity.id,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error adding activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def add_activity_bulk(request):
    """API สำหรับเพิ่มกิจกรรมหลายรายการพร้อมกัน"""
    try:
        data = json.loads(request.body)
        activity_data = data.get("activity", [])

        created_activity = []
        for activity_data in activity_data:
            # แปลงเวลาจาก string เป็น time object
            start_time = parse_time_flexible(
                activity_data.get("start_time_activity"), "08:00"
            )
            stop_time = parse_time_flexible(
                activity_data.get("stop_time_activity"), "09:00"
            )

            activity = WeekActivity.objects.create(
                act_name_activity=activity_data.get("act_name_activity"),
                day_activity=activity_data.get("day_activity", ""),
                start_time_activity=start_time,
                stop_time_activity=stop_time,
            )
            created_activity.append(activity.id)

        return JsonResponse(
            {
                "status": "success",
                "message": f"เพิ่มกิจกรรม {len(created_activity)} รายการสำเร็จ",
                "created_ids": created_activity,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error adding activity bulk: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["PUT"])
def update_activity(request, id):
    """API สำหรับแก้ไขกิจกรรม"""
    try:
        activity = WeekActivity.objects.get(id=id)
        data = json.loads(request.body)

        activity.act_name_activity = data.get(
            "act_name_activity", activity.act_name_activity
        )
        activity.day_activity = data.get("day_activity", activity.day_activity)

        # แปลงเวลาถ้ามีการส่งมา
        if data.get("start_time_activity"):
            activity.start_time_activity = parse_time_flexible(
                data.get("start_time_activity"), "08:00"
            )
        if data.get("stop_time_activity"):
            activity.stop_time_activity = parse_time_flexible(
                data.get("stop_time_activity"), "09:00"
            )

        activity.save()

        return JsonResponse(
            {"status": "success", "message": "แก้ไขกิจกรรมสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )
    except WeekActivity.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลกิจกรรม"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error updating activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_activity(request, id):
    """API สำหรับลบกิจกรรม"""
    try:
        activity = WeekActivity.objects.get(id=id)
        activity.delete()

        return JsonResponse(
            {"status": "success", "message": "ลบกิจกรรมสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )
    except WeekActivity.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลกิจกรรม"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


@csrf_exempt
@require_http_methods(["POST"])
def upload_activity_csv(request):
    """API สำหรับอัปโหลดไฟล์ CSV กิจกรรม"""
    try:
        if "file" not in request.FILES:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบไฟล์ที่อัปโหลด"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        csv_file = request.FILES["file"]

        if not csv_file.name.endswith(".csv"):
            return JsonResponse(
                {"status": "error", "message": "กรุณาอัปโหลดไฟล์ CSV เท่านั้น"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        # อ่านไฟล์ CSV พร้อมจัดการ encoding
        try:
            decoded_file = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            for enc in ("utf-8", "cp874", "tis-620", "cp1252"):
                try:
                    csv_file.seek(0)
                    decoded_file = csv_file.read().decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

        csv_data = StringIO(decoded_file)
        reader = csv.DictReader(csv_data)

        created_count = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                WeekActivity.objects.create(
                    act_name_activity=norm(row.get("act_name_activity", "")),
                    day_activity=norm(row.get("day_activity", "")),
                    start_time_activity=parse_time_flexible(
                        row.get("start_time_activity"), "08:00"
                    ),
                    stop_time_activity=parse_time_flexible(
                        row.get("stop_time_activity"), "09:00"
                    ),
                )
                created_count += 1
            except Exception as e:
                errors.append(f"แถว {row_num}: {str(e)}")

        if errors:
            return JsonResponse(
                {
                    "status": "partial_success",
                    "message": f"อัปโหลดสำเร็จ {created_count} รายการ แต่มีข้อผิดพลาด {len(errors)} รายการ",
                    "created_count": created_count,
                    "errors": errors[:10],
                },
                json_dumps_params={"ensure_ascii": False},
            )

        return JsonResponse(
            {
                "status": "success",
                "message": f"อัปโหลดกิจกรรมสำเร็จ {created_count} รายการ",
                "created_count": created_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error uploading activity CSV: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )



# ========== Time Parsing Utility ==========


def parse_time_flexible(value, default_time="08:00"):
    """
    แปลงเวลาแบบยืดหยุ่น:
    - "8"     -> 08:00
    - "8:5"   -> 08:05
    - "8:30"  -> 08:30
    - "8.30"  -> 08:30   (ตีความส่วนหลังจุดเป็น 'นาที' ถ้า <= 59)
    - "8.5"   -> 08:30   (ตีความทศนิยมเป็น 'เศษชั่วโมง')
    - เว้นว่าง/None -> default_time
    """
    s = "" if value is None else str(value).strip()
    if s == "":
        s = default_time

    # ปรับโคลอนแบบฟูลวิธ และตัดช่องว่าง
    s = s.replace("：", ":").strip()

    # กรณีรูปแบบ HH:MM ปกติ
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError:
        pass

    # ถ้าไม่มีโคลอนเลย -> อาจเป็น "8" หรือ "8.5" หรือ "8.30"
    if ":" not in s:
        # กรณี "8.30" (จุดแปลว่านาที) หรือ "8.5" (ทศนิยมชั่วโมง)
        if "." in s:
            left, right = s.split(".", 1)
            if left.isdigit() and right.isdigit():
                # ตีความแบบ 'นาที' ก่อน หาก right <= 59
                hh = int(left)
                mm = int(right[:2])  # เอา 2 หลักแรก
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    return time(hh, mm)
            # ไม่ใช่นาที -> ลองตีความเป็นชั่วโมงทศนิยม
            try:
                f = float(s.replace(",", "."))
                if 0 <= f < 24:
                    hh = int(f)
                    mm = int(round((f - hh) * 60))
                    if mm == 60:
                        hh += 1
                        mm = 0
                    if 0 <= hh <= 23:
                        return time(hh, mm)
            except Exception:
                pass

        # กรณีเป็นตัวเลขล้วน "8" -> "08:00"
        if s.isdigit():
            hh = int(s)
            if 0 <= hh <= 23:
                return time(hh, 0)

        # อย่างอื่น แปลงไม่ได้ -> ใช้ดีฟอลต์
        return datetime.strptime(default_time, "%H:%M").time()

    # กรณีมีโคลอน แต่ไม่ครบ 2 หลัก เช่น "8:5" -> 08:05
    parts = s.split(":", 1)
    if all(p.strip().isdigit() for p in parts):
        hh = int(parts[0])
        mm = int(parts[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm)

    # สุดท้าย fallback
    return datetime.strptime(default_time, "%H:%M").time()


from datetime import datetime, date, timedelta


def compute_stop_str(start_str: str, hours_str: str) -> str:
    """
    รับ start_time ('HH:MM' หรือรูปแบบยืดหยุ่น) + ชั่วโมง (เช่น '2' หรือ '1.5')
    คืนค่าเวลาสิ้นสุดเป็นสตริง 'HH:MM' (คำนวณแบบข้ามวันได้)
    """
    try:
        start_t = parse_time_flexible(start_str, "08:00")
        h = float(hours_str or "0")
        if h <= 0:
            return ""
        end_dt = datetime.combine(date.today(), start_t) + timedelta(hours=h)
        return end_dt.strftime("%H:%M")
    except Exception:
        return ""


# ========== Download Schedule API ==========


@csrf_exempt
@require_http_methods(["GET"])
def download_schedule(request):
    """ดาวน์โหลดตารางสอนเป็น CSV (ใช้ Hour)"""
    try:
        # เหมือน DB:
        qs = ScheduleInfo.objects.order_by("id")

        import csv
        from io import StringIO

        buff = StringIO()
        writer = csv.DictWriter(
            buff,
            fieldnames=[
                "Course_Code",
                "Subject_Name",
                "Teacher",
                "Room",
                "Room_Type",
                "Type",
                "Day",
                "Hour",
            ],
        )
        writer.writeheader()
        for s in qs:
            writer.writerow(
                {
                    "Course_Code": s.Course_Code,
                    "Subject_Name": s.Subject_Name,
                    "Teacher": s.Teacher,
                    "Room": s.Room,
                    "Room_Type": s.Room_Type,
                    "Type": s.Type,
                    "Day": s.Day,
                    "Hour": s.Hour,
                }
            )

        csv_text = buff.getvalue()
        csv_bytes = ("\ufeff" + csv_text).encode(
            "utf-8-sig"
        )  # BOM เพื่อเปิดใน Excel ภาษาไทย

        from django.http import HttpResponse

        resp = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="schedule.csv"'
        return resp

    except Exception as e:
        logger.error(f"Error downloading schedule: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


# ========== Add info ==========
def add_info(request):
    """หน้าเพิ่มข้อมูล"""
    context = {"title": "เพิ่มข้อมูล"}
    return render(request, "add.html", context)


# ================ AddPIS ==================
# ========== Subjact ==========
def subject(request):
    return render(request, "subject.html", {"active_tab": "subject"})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def subjects_collection(request):
    if request.method == "GET":
        # subject.js คาดว่าได้ "list ของ object" ตรง ๆ
        items = list(Subject.objects.order_by("code").values("id", "code", "name"))
        return JsonResponse(
            items, safe=False, json_dumps_params={"ensure_ascii": False}
        )

    # POST: create (อิง code เป็น key, ถ้ามีอยู่แล้วให้อัปเดตชื่อ)
    data = json.loads(request.body or "{}")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        return JsonResponse({"message": "กรอก code และ name ให้ครบ"}, status=400)

    obj, created = Subject.objects.update_or_create(code=code, defaults={"name": name})
    return JsonResponse(
        {"id": obj.id, "created": created}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def subjects_detail(request, pk: int):
    # PUT: update by id
    if request.method == "PUT":
        try:
            obj = Subject.objects.get(pk=pk)
        except Subject.DoesNotExist:
            return JsonResponse({"message": "ไม่พบรายวิชา"}, status=404)

        data = json.loads(request.body or "{}")
        code = (data.get("code") or "").strip().upper()
        name = (data.get("name") or "").strip()
        if not code or not name:
            return JsonResponse({"message": "กรอก code และ name ให้ครบ"}, status=400)

        obj.code, obj.name = code, name
        obj.save(update_fields=["code", "name"])
        return JsonResponse(
            {"id": obj.id, "updated": True}, json_dumps_params={"ensure_ascii": False}
        )

    # DELETE: delete by id
    deleted, _ = Subject.objects.filter(pk=pk).delete()
    if not deleted:
        return JsonResponse({"message": "ไม่พบรายวิชา"}, status=404)
    return JsonResponse({"deleted": True})

@csrf_exempt
@require_http_methods(["DELETE"])
def subject_delete_all(request):
    try:
        deleted_count, _ = Subject.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ Subject ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})




# ========== Teacher ==========
def teacher(request):
    return render(request, "teacher.html", {"active_tab": "teacher"})


@require_http_methods(["GET"])
def teacher_list(request):
    qs = Teacher.objects.order_by("id")
    items = [{"id": t.id, "name": t.name} for t in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


# ---------- Teacher: ADD ----------
@csrf_exempt
@require_http_methods(["POST"])
def teacher_add(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "รูปแบบข้อมูลไม่ถูกต้อง"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse(
            {"status": "error", "message": "ชื่ออาจารย์ห้ามว่าง"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    # กันชื่อซ้ำ (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
    if Teacher.objects.filter(name__iexact=name).exists():
        return JsonResponse(
            {"status": "error", "message": "มีชื่ออาจารย์นี้อยู่แล้ว"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    t = Teacher.objects.create(name=name)
    return JsonResponse(
        {"status": "success", "id": t.id, "name": t.name},
        json_dumps_params={"ensure_ascii": False},
    )


# ---------- Teacher: UPDATE ----------
@csrf_exempt
@require_http_methods(["PUT"])
def teacher_update(request, pk):
    # หาเรคคอร์ด
    try:
        t = Teacher.objects.get(pk=pk)
    except Teacher.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบอาจารย์"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )

    # อ่าน JSON
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "รูปแบบข้อมูลไม่ถูกต้อง"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse(
            {"status": "error", "message": "ชื่ออาจารย์ห้ามว่าง"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    # กันชื่อซ้ำ (ยกเว้นตัวเอง)
    if Teacher.objects.exclude(pk=pk).filter(name__iexact=name).exists():
        return JsonResponse(
            {"status": "error", "message": "มีชื่ออาจารย์นี้อยู่แล้ว"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    # อัปเดต
    t.name = name
    t.save()
    return JsonResponse(
        {"status": "success", "id": t.id, "name": t.name},
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_http_methods(["DELETE"])
def teacher_delete_all(request):
    try:
        deleted_count, _ = Teacher.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ Teacher ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})

@csrf_exempt
@require_http_methods(["DELETE"])
def teacher_delete(request, pk):
    Teacher.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})


# ========== Student Group ==========
def studentgroup(request):
    return render(request, "studentgroup.html", {"active_tab": "studentgroup"})


@require_http_methods(["GET"])
def studentgroup_list(request):
    qs = StudentGroup.objects.select_related("group_type").order_by("id")
    items = [
        {
            "id": sg.id,
            "name": sg.name,
            "type": sg.group_type_id,  # ให้สอดคล้องกับ key 'type' ในฟอร์ม
            "type_name": sg.group_type.name if sg.group_type_id else "",
        }
        for sg in qs
    ]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def studentgroup_add(request):
    data = json.loads(request.body or "{}")
    raw_id = data.get("id")  # ผู้ใช้กรอกเอง (required ในฟอร์ม)
    name = (data.get("name") or "").strip()
    type_id = data.get("type")

    # ตรวจค่าบังคับ
    if raw_id is None or str(raw_id).strip() == "":
        return JsonResponse(
            {"status": "error", "message": "รหัสกลุ่มนักศึกษา (id) ห้ามว่าง"}, status=400
        )
    try:
        pk = int(raw_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"status": "error", "message": "รหัสกลุ่มนักศึกษาต้องเป็นตัวเลข"}, status=400
        )

    if not name or not type_id:
        return JsonResponse(
            {"status": "error", "message": "name และ type ห้ามว่าง"}, status=400
        )
    # เช็กว่า GroupType มีจริง
    if not GroupType.objects.filter(pk=type_id).exists():
        return JsonResponse(
            {"status": "error", "message": "ไม่พบประเภทนักศึกษาที่เลือก"}, status=400
        )

    # upsert ตาม id (ผู้ใช้กำหนด pk เองตามฟอร์ม)
    obj, _created = StudentGroup.objects.update_or_create(
        id=pk,
        defaults={"name": name, "group_type_id": type_id},
    )
    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@csrf_exempt
@require_http_methods(["DELETE"])
def grouptype_delete_all(request):
    """API สำหรับลบ GroupType ทั้งหมด"""
    try:
        from .models import GroupType  # ถ้ายังไม่ได้ import ไว้
        deleted_count, _ = GroupType.objects.all().delete()
        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบ GroupType ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting all GroupType: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["DELETE"])
def studentgroup_delete(request, pk):
    StudentGroup.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})

@csrf_exempt
@require_http_methods(["DELETE"])
def studentgroup_delete_all(request):
    try:
        deleted_count, _ = StudentGroup.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ StudentGroup ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})


# ========== Group Type ==========
def grouptype(request):
    return render(request, "grouptype.html", {"active_tab": "grouptype"})


@require_http_methods(["GET"])
def grouptype_list(request):
    qs = GroupType.objects.order_by("id")
    items = [{"id": x.id, "type": x.name} for x in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def grouptype_add(request):
    data = json.loads(request.body or "{}")
    # รับมาจากฟอร์ม: id (ตัวเลข) และ type (string)
    raw_id = data.get("id")
    type_name = (data.get("type") or "").strip()

    if not raw_id:
        return JsonResponse(
            {"status": "error", "message": "รหัสภาค (id) ห้ามว่าง"}, status=400
        )
    try:
        gid = int(raw_id)
    except Exception:
        return JsonResponse(
            {"status": "error", "message": "รหัสภาคต้องเป็นตัวเลข"}, status=400
        )

    if not type_name:
        return JsonResponse(
            {"status": "error", "message": "ประเภทนักศึกษา (type) ห้ามว่าง"}, status=400
        )

    # upsert ตาม id: ถ้ามีแล้วให้แก้ชื่อ, ถ้าไม่มีให้สร้างใหม่ด้วย pk นั้น
    obj, _created = GroupType.objects.update_or_create(
        id=gid,
        defaults={"name": type_name},
    )
    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@csrf_exempt
@require_http_methods(["DELETE"])
def grouptype_delete_all(request):
    """API สำหรับลบ GroupType ทั้งหมด"""
    try:
        from .models import GroupType  # ถ้ายังไม่ได้ import ไว้
        deleted_count, _ = GroupType.objects.all().delete()
        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบ GroupType ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting all GroupType: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["DELETE"])
def grouptype_delete(request, pk):
    GroupType.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})


# ========== Group Allow ==========
def groupallow(request):
    return render(request, "groupallow.html", {"active_tab": "groupallow"})


@require_http_methods(["GET"])
def groupallow_list(request):
    qs = GroupAllow.objects.select_related("group_type", "slot").order_by("id")
    items = []
    for x in qs:
        items.append(
            {
                "id": x.id,
                # ให้สอดคล้องกับหน้าคุณที่ใช้ key 'dept' และ 'slot'
                "dept": x.group_type_id,
                "slot": x.slot_id,
                # เผื่ออยากโชว์สวย ๆ ในอนาคต
                "dept_name": x.group_type.name if x.group_type_id else "",
                "slot_text": str(x.slot) if x.slot_id else "",
            }
        )
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def groupallow_add(request):
    data = json.loads(request.body or "{}")
    group_type_id = data.get("dept")
    slot_id = data.get("slot")
    if not group_type_id or not slot_id:
        return JsonResponse(
            {"status": "error", "message": "dept และ slot ห้ามว่าง"}, status=400
        )

    # ป้องกันซ้ำตาม unique_together
    obj, created = GroupAllow.objects.get_or_create(
        group_type_id=group_type_id,
        slot_id=slot_id,
    )
    return JsonResponse(
        {"status": "success", "id": obj.id, "created": created},
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_http_methods(["DELETE"])
def groupallow_delete(request, pk):
    GroupAllow.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})

@csrf_exempt
@require_http_methods(["DELETE"])
def groupallow_delete_all(request):
    """API สำหรับลบ GroupAllow ทั้งหมด"""
    try:
        deleted_count, _ = GroupAllow.objects.all().delete()
        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบ GroupAllow ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error deleting all GroupAllow: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )


# ========== Rooom ==========
def room(request):
    return render(request, "room.html", {"active_tab": "room"})


@require_http_methods(["GET"])
def room_list(request):
    qs = Room.objects.select_related("room_type").order_by("id")
    items = [
        {
            "id": r.id,
            "name": r.name,
            "type": r.room_type_id,
            "type_name": r.room_type.name if r.room_type_id else "",
        }
        for r in qs
    ]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def room_add(request):
    data = json.loads(request.body or "{}")
    raw_id = data.get("id")  # optional
    name = (data.get("name") or "").strip()
    type_id = data.get("type")

    if not name or not type_id:
        return JsonResponse(
            {"status": "error", "message": "name และ type ห้ามว่าง"}, status=400
        )

    if raw_id:
        try:
            rid = int(raw_id)
        except Exception:
            return JsonResponse(
                {"status": "error", "message": "รหัสห้อง (id) ต้องเป็นตัวเลข"}, status=400
            )
        obj, _created = Room.objects.update_or_create(
            id=rid, defaults={"name": name, "room_type_id": type_id}
        )
    else:
        obj = Room.objects.create(name=name, room_type_id=type_id)

    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["DELETE"])
def room_delete_all(request):
    """ลบห้องเรียนทั้งหมด"""
    try:
        deleted_count, _ = Room.objects.all().delete()
        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบห้องเรียนทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "error",
                "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}",
            },
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["DELETE"])
def room_delete(request, pk):
    Room.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})


# ========== Rooom Type ==========
def roomtype(request):
    return render(request, "roomtype.html", {"active_tab": "roomtype"})


@require_http_methods(["GET"])
def roomtype_list(request):
    qs = RoomType.objects.order_by("id")
    items = [{"id": x.id, "name": x.name} for x in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def roomtype_add(request):
    data = json.loads(request.body or "{}")
    raw_id = data.get("id")  # optional
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"status": "error", "message": "name ห้ามว่าง"}, status=400)

    if raw_id:
        try:
            pk = int(raw_id)
        except Exception:
            return JsonResponse(
                {"status": "error", "message": "รหัสประเภทห้อง (id) ต้องเป็นตัวเลข"},
                status=400,
            )
        obj, _created = RoomType.objects.update_or_create(
            id=pk, defaults={"name": name}
        )
    else:
        obj = RoomType.objects.create(name=name)

    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@csrf_exempt
@require_http_methods(["DELETE"])
def roomtype_delete_all(request):
    """API สำหรับลบ RoomType ทั้งหมด"""
    try:
        deleted_count, _ = RoomType.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ RoomType ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_http_methods(["DELETE"])
def roomtype_delete(request, pk):
    RoomType.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})


# ========== Time Slot ==========
def timeslot(request):
    return render(request, "timeslot.html", {"active_tab": "timeslot"})


# DAY_MAP = {
#     "จันทร์": "Mon",
#     "อังคาร": "Tue",
#     "พุธ": "Wed",
#     "พฤหัสบดี": "Thu",
#     "ศุกร์": "Fri",
#     "เสาร์": "Sat",
#     "อาทิตย์": "Sun",
#     "Mon": "Mon",
#     "Tue": "Tue",
#     "Wed": "Wed",
#     "Thu": "Thu",
#     "Fri": "Fri",
#     "Sat": "Sat",
#     "Sun": "Sun",
# }


# def _norm_day(val: str):
#     if not val:
#         return None
#     v = str(val).strip()
#     if v in DAY_MAP:
#         return DAY_MAP[v]
#     up = v[:1].upper() + v[1:].lower()
#     return DAY_MAP.get(up)

DAY_THAI = {
    "จันทร์": "จันทร์",
    "อังคาร": "อังคาร",
    "พุธ": "พุธ",
    "พฤหัสบดี": "พฤหัสบดี",
    "ศุกร์": "ศุกร์",
    "เสาร์": "เสาร์",
    "อาทิตย์": "อาทิตย์",
    # รองรับกรณีพิมพ์อังกฤษเข้ามา → แปลงเป็นไทย
    "Mon": "จันทร์",
    "Tue": "อังคาร",
    "Wed": "พุธ",
    "Thu": "พฤหัสบดี",
    "Fri": "ศุกร์",
    "Sat": "เสาร์",
    "Sun": "อาทิตย์",
}


def _norm_day(val: str):
    if not val:
        return None
    v = str(val).strip()
    return DAY_THAI.get(v, v)  # ถ้าไม่เจอ map ก็คืนค่าที่ส่งมาเลย


def _hhmm(t):
    return t.strftime("%H:%M") if t else ""


@require_http_methods(["GET"])
def timeslot_list(request):
    qs = TimeSlot.objects.order_by("day_of_week", "start_time")
    items = [
        {
            "id": x.id,
            "day": x.day_of_week,
            "start": _hhmm(x.start_time),
            "end": _hhmm(x.stop_time),
        }
        for x in qs
    ]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@csrf_exempt
@require_http_methods(["POST"])
def timeslot_add(request):
    data = json.loads(request.body or "{}")
    raw_id = data.get("id")
    day = _norm_day(data.get("day"))
    start = parse_time(str(data.get("start") or "").strip())
    end = parse_time(str(data.get("end") or "").strip())

    if raw_id is None or str(raw_id).strip() == "":
        return JsonResponse(
            {"status": "error", "message": "รหัสคาบ (id) ห้ามว่าง"}, status=400
        )
    try:
        pk = int(raw_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"status": "error", "message": "รหัสคาบต้องเป็นตัวเลข"}, status=400
        )

    if not day or not start or not end:
        return JsonResponse(
            {
                "status": "error",
                "message": "กรอกวัน/เวลาให้ครบและถูกต้อง (รูปแบบเวลา HH:MM)",
            },
            status=400,
        )
    if start >= end:
        return JsonResponse(
            {"status": "error", "message": "เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด"}, status=400
        )

    try:
        obj, _created = TimeSlot.objects.update_or_create(
            id=pk,
            defaults={"day_of_week": day, "start_time": start, "stop_time": end},
        )
    except IntegrityError:
        return JsonResponse(
            {"status": "error", "message": "มีคาบ (วัน+เวลา) นี้อยู่แล้ว"}, status=400
        )

    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@csrf_exempt
@require_http_methods(["DELETE"])
def timeslot_delete_all(request):
    try:
        deleted_count, _ = TimeSlot.objects.all().delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ TimeSlot ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})

@csrf_exempt
@require_http_methods(["DELETE"])
def timeslot_delete(request, pk):
    TimeSlot.objects.filter(pk=pk).delete()
    return JsonResponse({"status": "success"})


# ลำดับวันสำหรับ sort
# _DAY_ORDER = {"Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6, "Sun": 7}
_DAY_ORDER = {
    "จันทร์": 1,
    "อังคาร": 2,
    "พุธ": 3,
    "พฤหัสบดี": 4,
    "ศุกร์": 5,
    "เสาร์": 6,
    "อาทิตย์": 7,
}
# แม็พ code -> ชื่อไทย จาก DAY_CHOICES ใน models
_DAY_THAI = dict(DAY_CHOICES)


# ========== META (สำหรับดรอปดาวน์หน้า weekactivity) ==========
@require_http_methods(["GET"])
def meta_days(request):
    # คืนวันเฉพาะที่มีใน TimeSlot จริง เพื่อไม่ให้เลือกวันลอย ๆ
    codes = TimeSlot.objects.values_list("day_of_week", flat=True).distinct()
    days = sorted(set(codes), key=lambda c: _DAY_ORDER.get(c, 99))
    payload = [{"value": c, "text": _DAY_THAI.get(c, c)} for c in days]
    return JsonResponse({"days": payload}, json_dumps_params={"ensure_ascii": False})


@require_http_methods(["GET"])
def meta_start_times(request):
    # input: ?day=Mon   (รองรับไทย เช่น "จันทร์" ด้วย)
    day = _norm_day(request.GET.get("day"))
    if not day:
        return JsonResponse(
            {"start_times": []}, json_dumps_params={"ensure_ascii": False}
        )
    times = (
        TimeSlot.objects.filter(day_of_week=day)
        .order_by("start_time")
        .values_list("start_time", flat=True)
        .distinct()
    )
    payload = [
        {"value": t.strftime("%H:%M"), "text": t.strftime("%H:%M")} for t in times
    ]
    return JsonResponse(
        {"start_times": payload}, json_dumps_params={"ensure_ascii": False}
    )


@require_http_methods(["GET"])
def meta_stop_times(request):
    # inputs: ?day=Mon&start=08:00
    day = _norm_day(request.GET.get("day"))
    start = parse_time(str(request.GET.get("start") or "").strip())
    if not day or not start:
        return JsonResponse(
            {"stop_times": []}, json_dumps_params={"ensure_ascii": False}
        )

    times = (
        TimeSlot.objects.filter(day_of_week=day, start_time=start)
        .order_by("stop_time")
        .values_list("stop_time", flat=True)
        .distinct()
    )
    payload = [
        {"value": t.strftime("%H:%M"), "text": t.strftime("%H:%M")} for t in times
    ]
    return JsonResponse(
        {"stop_times": payload}, json_dumps_params={"ensure_ascii": False}
    )


@require_GET
def teachers_lookup(request):
    # ใช้ฟอร์แมตเดียวกับ teacher_list เพื่อลดความเสี่ยง front-end พัง
    qs = Teacher.objects.order_by("id")
    items = [{"id": t.id, "name": t.name} for t in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@require_GET
def room_types_lookup(request):
    qs = RoomType.objects.order_by("id")
    items = [{"id": x.id, "name": x.name} for x in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )


@require_GET
def student_groups_lookup(request):
    # ส่งทั้ง id และ name (พอเพียงสำหรับ dropdown); ถ้าต้องใช้ type เพิ่มเติม ค่อยขยายทีหลัง
    qs = StudentGroup.objects.select_related("group_type").order_by("id")
    items = [{"id": g.id, "name": g.name} for g in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )

@require_http_methods(["GET"])
def list_generated_entities_api(request):
    from .models import GeneratedSchedule

    view = (request.GET.get("view") or "teacher").lower().strip()
    field_map = {
        "teacher": "teacher",
        "room": "room",
        "subject": "subject_name",
        "group": "student_group",
    }
    field = field_map.get(view, "teacher")

    q = (request.GET.get("q") or "").strip()
    qs = GeneratedSchedule.objects.all()
    if q:
        qs = qs.filter(**{f"{field}__icontains": q})

    rows = (qs.values(field).annotate(items=Count("id")).order_by(field))
    results = [{"key": r[field] or "N/A", "display": r[field] or "N/A", "count": r["items"]} for r in rows]

    return JsonResponse({"status": "success", "view": view, "results": results},
                        json_dumps_params={"ensure_ascii": False})
