import csv
import json
import logging
import os
import re
from datetime import datetime, date, time, timedelta
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
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
# --- เพิ่มมาใหม่สำหรับ PDF ---
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from django.http import HttpResponse
from django.template.loader import render_to_string

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from decimal import Decimal
import math

# views.py
from .main import run_genetic_algorithm_from_db, GenerationCancelled
from .models import WeekActivity, PreSchedule, CourseSchedule, ScheduleInfo

from threading import Event, Lock
from django.views.decorators.http import require_POST

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
    GeneratedSchedule
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

def _overlap_q(day_field, start_field, stop_field, day, start, stop):
    """
    ชน = วันเดียวกัน และ max(startA,startB) < min(stopA,stopB)
    """
    return Q(**{day_field: day}) & Q(**{start_field + "__lt": stop}) & Q(**{stop_field + "__gt": start})


def slot_start_hour(ts: str) -> int:
    m = re.search(r"(\d{1,2})(?::\d{2})?", ts or "")
    return int(m.group(1)) if m else 0

# close ga 
cancel_event = Event()
generation_lock = Lock()
generation_running = False

@login_required(login_url="/login/")
@require_POST
def cancel_generation(request):
    cancel_event.set()
    return HttpResponse(status=204)

# -------------------- GA generate --------------------
@login_required(login_url="/login/")
@require_http_methods(["POST"])
def generate_schedule_api(request):
    """
    รัน GA แบบ ผูก user + กันรันซ้อน + ยกเลิกได้
    * ต้องแก้ใน main.run_genetic_algorithm_from_db(...) ให้รับ user และ filter ด้วย created_by=user
    """
    global generation_running
    if not generation_lock.acquire(blocking=False):
        return JsonResponse({"status": "busy", "message": "already running"}, status=409)

    try:
        if generation_running:
            return JsonResponse({"status": "busy", "message": "already running"}, status=409)

        generation_running = True
        cancel_event.clear()

        try:
            result = run_genetic_algorithm_from_db(request.user, cancel_event=cancel_event)
            return JsonResponse(_san(result), json_dumps_params={"ensure_ascii": False})

        except GenerationCancelled:
            return HttpResponse(status=204)

        except Exception as e:
            logger.exception(f"[{request.user}] GA error")
            return JsonResponse({"status": "error", "message": str(e)}, status=500,
                                json_dumps_params={"ensure_ascii": False})
    finally:
        generation_running = False
        cancel_event.clear()
        generation_lock.release()

# ------------------------- pages -------------------------
@login_required(login_url="/login/")
def home(request):
    courses = CourseSchedule.objects.filter(created_by=request.user)
    context = {
        "title": "ระบบจัดการสอน",
        "total_teachers": courses.values("teacher_name_course").distinct().count(),
        "total_subjects": courses.values("subject_code_course").distinct().count(),
        "total_rooms": Room.objects.filter(created_by=request.user).count(),
        "total_activity": WeekActivity.objects.filter(created_by=request.user).count(),
        "generated_schedules": (
            GeneratedSchedule.objects
            .filter(created_by=request.user)
            .order_by("day_of_week", "start_time", "subject_code")
        ),
    }
    return render(request, "index.html", context)

@login_required(login_url="/login/")
def course_page(request):
    courses = CourseSchedule.objects.filter(created_by=request.user).order_by("id")
    return render(request, "course.html", {"title": "จัดการข้อมูลรายวิชา", "courses": courses})

@login_required(login_url="/login/")
def activity_page(request):
    activity = WeekActivity.objects.filter(created_by=request.user)
    return render(request, "weekactivity.html", {"title": "จัดการกิจกรรม", "activity": activity})

@login_required(login_url="/login/")
def pre_page(request):
    pre_schedules = PreSchedule.objects.filter(created_by=request.user)
    return render(request, "pre.html", {"title": "จัดการตารางล่วงหน้า", "pre_schedules": pre_schedules})

def add_info(request):
    return render(request, "add.html", {"title": "เพิ่มข้อมูล"})

@login_required(login_url="/login/")
def subject(request):
    return render(request, "subject.html", {"active_tab": "subject"})

@login_required(login_url="/login/")
def teacher(request):
    return render(request, "teacher.html", {"active_tab": "teacher"})

@login_required(login_url="/login/")
def studentgroup(request):
    return render(request, "studentgroup.html", {"active_tab": "studentgroup"})

@login_required(login_url="/login/")
def grouptype(request):
    return render(request, "grouptype.html", {"active_tab": "grouptype"})

@login_required(login_url="/login/")
def groupallow(request):
    return render(request, "groupallow.html", {"active_tab": "groupallow"})

@login_required(login_url="/login/")
def room(request):
    return render(request, "room.html", {"active_tab": "room"})

@login_required(login_url="/login/")
def roomtype(request):
    return render(request, "roomtype.html", {"active_tab": "roomtype"})

@login_required(login_url="/login/")
def timeslot(request):
    return render(request, "timeslot.html", {"active_tab": "timeslot"})

@login_required(login_url="/login/")
def about(request):
    return render(request, "about.html", {"active_tab": "about"})

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

# -------------------- GA generate --------------------
@login_required(login_url="/login/")
@require_http_methods(["POST"])
def generate_schedule_api(request):
    """
    รัน GA แบบ ผูก user + กันรันซ้อน + ยกเลิกได้
    * ต้องแก้ใน main.run_genetic_algorithm_from_db(...) ให้รับ user และ filter ด้วย created_by=user
    """
    global generation_running
    if not generation_lock.acquire(blocking=False):
        return JsonResponse({"status": "busy", "message": "already running"}, status=409)

    try:
        if generation_running:
            return JsonResponse({"status": "busy", "message": "already running"}, status=409)

        generation_running = True
        cancel_event.clear()

        try:
            result = run_genetic_algorithm_from_db(cancel_event=cancel_event, user=request.user)
            return JsonResponse(_san(result), json_dumps_params={"ensure_ascii": False})

        except GenerationCancelled:
            return HttpResponse(status=204)

        except Exception as e:
            logger.exception(f"[{request.user}] GA error")
            return JsonResponse({"status": "error", "message": str(e)}, status=500,
                                json_dumps_params={"ensure_ascii": False})
    finally:
        generation_running = False
        cancel_event.clear()
        generation_lock.release()
# ========== View Schedule API ==========

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def test_program_api(request):
    """API สำหรับทดสอบระบบ"""
    try:
        course_count = CourseSchedule.objects.filter(created_by=request.user).count()
        return JsonResponse(
            {
                "status": "success",
                "message": "ระบบทำงานปกติ",
                "data": {
                    "courses": course_count,
                    "timestamp": datetime.now().isoformat(),
                    "user": request.user.username,
                },
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"[test_program_api] Error: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

# ---------------- schedule views ----------------
@login_required(login_url="/login/")
@require_http_methods(["GET"])
def view_schedule_api(request):
    try:
        qs = ScheduleInfo.objects.filter(created_by=request.user).order_by("Day", "Hour", "id")
        schedules = [{
            "id": s.id,
            "Course_Code": s.Course_Code,
            "Subject_Name": s.Subject_Name,
            "Teacher": s.Teacher,
            "Room": s.Room,
            "Room_Type": s.Room_Type,
            "Type": s.Type,
            "Day": s.Day,
            "Hour": s.Hour,
            "Time_Slot": s.Time_Slot,
        } for s in qs]
        return JsonResponse({"status": "success", "total_entries": len(schedules), "schedules": schedules},
                            json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        logger.error(f"[{request.user}] view_schedule_api error: {e}")
        return JsonResponse({"status": "error", "message": f"ไม่สามารถดึงข้อมูลได้: {e}"},
                            status=500, json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def view_generated_schedule_api(request):
    try:
        qs = GeneratedSchedule.objects.filter(created_by=request.user)\
                                      .order_by("day_of_week", "start_time", "id")
        schedules = [{
            "Course_Code": g.subject_code or "",
            "Subject_Name": g.subject_name or "",
            "Teacher": g.teacher or "",
            "Room": g.room or "",
            "Type": g.type or "",
            "Student_Group": g.student_group or "",
            "Day": g.day_of_week or "",
            "StartTime": g.start_time.strftime("%H:%M") if g.start_time else "",
            "StopTime": g.stop_time.strftime("%H:%M") if g.stop_time else "",
            "Hour": int(g.start_time.strftime("%H")) if g.start_time else None,
        } for g in qs]
        return JsonResponse({"status": "success", "total_entries": len(schedules), "schedules": schedules},
                            json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        logger.error(f"[{request.user}] view_generated_schedule_api error: {e}")
        return JsonResponse({"status": "error", "message": f"ไม่สามารถดึงข้อมูลที่สร้างแล้วได้: {e}"},
                            status=500, json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def list_generated_schedules(request):
    try:
        qs = (GeneratedSchedule.objects.filter(created_by=request.user)
              .order_by("-id")
              .values("id","teacher","subject_code","subject_name","type",
                      "student_group","hours","section","day_of_week",
                      "start_time","stop_time","room"))
        items = []
        for r in qs:
            r["start_time"] = r["start_time"].strftime("%H:%M") if r["start_time"] else ""
            r["stop_time"]  = r["stop_time"].strftime("%H:%M")  if r["stop_time"]  else ""
            items.append(r)
        return JsonResponse({"status": "success", "results": items})
    except Exception as e:
        logger.error(f"[{request.user}] list_generated_schedules error: {e}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500,
                            json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["POST"])
def delete_generated_selected(request):
    """รับ {"schedule_ids":[...]} และลบเฉพาะของ user นี้"""
    try:
        payload = json.loads(request.body or "{}")
        ids = payload.get("schedule_ids", [])
        if not isinstance(ids, list):
            return HttpResponseBadRequest("schedule_ids ต้องเป็น list")
        qs = GeneratedSchedule.objects.filter(id__in=ids, created_by=request.user)
        deleted_count, _ = qs.delete()
        return JsonResponse({"status": "success",
                             "message": f"ลบตาราง {deleted_count} รายการสำเร็จ",
                             "deleted_count": deleted_count},
                            json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        logger.error(f"[{request.user}] delete_generated_selected error: {e}")
        return JsonResponse({"status":"error","message":f"เกิดข้อผิดพลาดในการลบ: {e}"},
                            status=500, json_dumps_params={"ensure_ascii": False})

    
# ========== COURSE APIs ==========
def _teacher_name_from_id(raw):
    try: tid = int(raw)
    except (TypeError, ValueError): return ""
    t = Teacher.objects.filter(id=tid).only("name").first()
    return t.name if t else ""

@login_required(login_url="/login/")
@require_http_methods(["GET"])
@csrf_exempt
def get_courses(request):
    """API สำหรับดึงข้อมูลรายวิชาทั้งหมด"""
    try:
        qs = CourseSchedule.objects.filter(created_by=request.user)
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

@login_required(login_url="/login/")
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
            subject_code_course=code, 
            section_course=section,
            created_by=request.user
        ).exists():
            return JsonResponse(
                {"status": "error", "message": f"วิชา {code} กลุ่ม {section} มีอยู่แล้ว"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        code_in = norm_code(data.get("subject_code_course", ""))
        section_in = (data.get("section_course") or "").strip()

        if code_in and section_in:
            pre_exists = PreSchedule.objects.filter(
                subject_code_pre=code_in,
                section_pre=section_in,
                created_by=request.user,
            ).exists()
            if pre_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"วิชา {code_in} กลุ่ม {section_in} มีอยู่แล้วในหน้า Pre "
                            f"กรุณาจัดการที่หน้าเดียวเท่านั้น"
                        ),
                    },
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
            created_by=request.user  # ✅ บันทึกว่า user ไหนเป็นคนเพิ่ม
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def add_course_bulk(request):
    """API สำหรับเพิ่มรายวิชาหลายรายการพร้อมกัน (เฉพาะของ user ปัจจุบัน)"""
    try:
        data = json.loads(request.body or "{}")
        rows = data.get("courses", data.get("course", []))

        if not rows:
            return JsonResponse(
                {"status": "error", "message": "ไม่มีข้อมูลรายวิชาในคำขอ"},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        created_ids = []
        duplicate_list = []

        for row in rows:
            def g(key_simple, key_old):
                return row.get(key_simple, row.get(key_old))

            code = norm_code(g("subject_code", "subject_code_course"))
            section = (g("section", "section_course") or "").strip()

            if not code or not section:
                continue  # ข้ามถ้าข้อมูลไม่ครบ

            # 🔸 กันซ้ำใน scope ของ user
            if CourseSchedule.objects.filter(
                subject_code_course=code,
                section_course=section,
                created_by=request.user
            ).exists():
                duplicate_list.append(f"{code} (sec {section})")
                continue



            teacher_name = (
                _teacher_name_from_id(row.get("teacher_id"))
                or row.get("teacher_name")
                or row.get("teacher_name_course")
            )

            c = CourseSchedule.objects.create(
                teacher_name_course=teacher_name,
                subject_code_course=code,
                subject_name_course=g("subject_name", "subject_name_course"),
                student_group_name_course=g("student_group_id", "student_group_name_course") or "",
                room_type_course=g("room_type", "room_type_course") or "",
                section_course=section,
                theory_slot_amount_course=to_int(g("theory_hours", "theory_slot_amount_course"), 0),
                lab_slot_amount_course=to_int(g("lab_hours", "lab_slot_amount_course"), 0),
                created_by=request.user,  # ✅ ผูกกับ user ปัจจุบัน
            )
            created_ids.append(c.id)

        msg = f"เพิ่มรายวิชา {len(created_ids)} รายการสำเร็จ"
        if duplicate_list:
            msg += f" (ข้าม {len(duplicate_list)} รายการซ้ำ: {', '.join(duplicate_list[:5])})"

        return JsonResponse(
            {"status": "success", "message": msg, "created_ids": created_ids},
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error adding course bulk: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )
    
@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def update_course(request, id):
    """API สำหรับแก้ไขรายวิชา (กันซ้ำ: วิชาเดียวกัน + sec เดียวกัน โดยยกเว้นแถวตัวเอง)"""
    try:
        course = CourseSchedule.objects.get(id=id, created_by=request.user)
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

        code_in = norm_code(data.get("subject_code_course", course.subject_code_course)) or course.subject_code_course
        section_in = (data.get("section_course", course.section_course) or "").strip()

        if code_in and section_in:
            pre_exists = PreSchedule.objects.filter(
                subject_code_pre=code_in,
                section_pre=section_in,
                created_by=request.user,
            ).exists()
            if pre_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"วิชา {code_in} กลุ่ม {section_in} มีอยู่แล้วในหน้า Pre "
                            f"กรุณาจัดการที่หน้าเดียวเท่านั้น"
                        ),
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def delete_course(request, id):
    """API สำหรับลบข้อมูลรายวิชา (เฉพาะของ user ปัจจุบัน)"""
    try:
        # ✅ ตรวจเฉพาะ course ของ user คนนั้น
        course = CourseSchedule.objects.filter(id=id, created_by=request.user).first()
        if not course:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบรายวิชานี้ หรือไม่มีสิทธิ์ลบ"},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )

        course.delete()

        return JsonResponse(
            {"status": "success", "message": "ลบข้อมูลรายวิชาสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error deleting course: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )
 
@login_required(login_url="/login/")
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def course_delete_all(request):
    """ลบรายวิชาทั้งหมดของ user ปัจจุบัน"""
    try:
        deleted_count, _ = CourseSchedule.objects.filter(
            created_by=request.user  # ✅ ลบเฉพาะของคนนี้
        ).delete()

        return JsonResponse(
            {
                "status": "success",
                "message": f"ลบรายวิชาทั้งหมดสำเร็จ ({deleted_count} รายการ)",
                "deleted_count": deleted_count,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error deleting all courses: {e}")
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

# ========== PRE-SCHEDULE APIs ==========
@login_required(login_url="/login/")
def pre_page(request):
    pre_schedules = PreSchedule.objects.filter(created_by=request.user)
    return render(request, "pre.html", {"pre_schedules": pre_schedules})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
@csrf_exempt
def get_pre(request):
    """API สำหรับดึงข้อมูลตารางล่วงหน้าทั้งหมด"""
    try:
        pre_schedules = PreSchedule.objects.filter(created_by=request.user)
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
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
                created_by=request.user,   # เฉพาะของ user คนนี้
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
                    day_pre=day, # วันเดียวกัน
                    created_by=request.user,   # เฉพาะของ user คนนี้
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
        
        if day:
            wk_overlap = (
                WeekActivity.objects
                .filter(created_by=request.user, day_activity=day)
                .filter(
                    Q(start_time_activity__lt=stop_time) &
                    Q(stop_time_activity__gt=start_time)
                )
                .exists()
            )
            if wk_overlap:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            f"เวลาทับกับ 'กิจกรรมประจำสัปดาห์' วัน {day} "
                            f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}"
                        ),
                    },
                    status=400,
                    json_dumps_params={"ensure_ascii": False},
                )

        if code and section_val:
            course_exists = CourseSchedule.objects.filter(
                subject_code_course=code,
                section_course=section_val,
                created_by=request.user,
            ).exists()
            if course_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"วิชา {code} กลุ่ม {section_val} มีอยู่แล้วในหน้า Course "
                                f"กรุณาจัดการที่หน้าเดียวเท่านั้น",
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
            created_by=request.user,   # ✅ ผูกกับ user
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def pre_delete_all(request):
    """API สำหรับลบ PreSchedule ทั้งหมด"""
    try:
        deleted_count, _ = PreSchedule.objects.filter(created_by=request.user).delete()
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def update_pre(request, id):
    """API สำหรับแก้ไขตารางล่วงหน้า (กันชนเวลา + กันซ้ำ วิชา/กลุ่ม/ภาคทฤษฎี-ปฏิบัติ[room_type_pre])"""
    try:
        pre = PreSchedule.objects.get(id=id, created_by=request.user)
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
                PreSchedule.objects.filter(room_name_pre=room_name_val, day_pre=day_val, created_by=request.user)
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
        
        wk_overlap = (
            WeekActivity.objects
            .filter(created_by=request.user, day_activity=day_val)
            .filter(Q(start_time_activity__lt=stop_time) & Q(stop_time_activity__gt=start_time))
            .exists()
        )
        if wk_overlap:
            return JsonResponse(
                {"status": "error",
                 "message": (f"เวลาทับกับ 'กิจกรรมประจำสัปดาห์' วัน {day_val} "
                             f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}")},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        if code_in and section_val:
            course_exists = CourseSchedule.objects.filter(
                subject_code_course=code_in,
                section_course=section_val,
                created_by=request.user,
            ).exists()
            if course_exists:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"วิชา {code_in} กลุ่ม {section_val} มีอยู่แล้วในหน้า Course "
                                f"กรุณาจัดการที่หน้าเดียวเท่านั้น",
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def delete_pre(request, id):
    """API สำหรับลบตารางล่วงหน้า"""
    try:
        pre = PreSchedule.objects.get(id=id, created_by=request.user)
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

@login_required(login_url="/login/")
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
def _overlap_exists(day, start_time, stop_time, exclude_id=None, created_by=None):
    qs = WeekActivity.objects.filter(day_activity=day)
    if created_by:
        qs = qs.filter(created_by=created_by)

    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    for w in qs:
        if (
            (start_time >= w.start_time_activity and start_time < w.stop_time_activity)
            or (stop_time > w.start_time_activity and stop_time <= w.stop_time_activity)
            or (start_time <= w.start_time_activity and stop_time >= w.stop_time_activity)
        ):
            return True
    return False

@login_required(login_url='/login/')
def weekactivity(request):
    return render(request, 'weekactivity.html', {"active_tab": "weekactivity"})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def activity_delete_all(request):
    """API สำหรับลบกิจกรรมทั้งหมดของ user ปัจจุบัน"""
    try:
        deleted_count, _ = WeekActivity.objects.filter(created_by=request.user).delete()
        return JsonResponse(
            {"status": "success", "message": f"ลบกิจกรรมทั้งหมดสำเร็จ ({deleted_count} รายการ)", "deleted_count": deleted_count}
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
def get_activity(request):
    """API สำหรับดึงข้อมูลกิจกรรมทั้งหมด"""
    try:
        activity = WeekActivity.objects.filter(created_by=request.user)
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def add_activity(request):
    """API สำหรับเพิ่มกิจกรรม (กันชื่อซ้ำ + กันเวลาทับในวันเดียวกัน)"""
    try:
        data = json.loads(request.body)

        name = (data.get("act_name_activity") or "").strip()
        day  = (data.get("day_activity") or "").strip()

        # แปลงเวลาจาก string -> time object (คุณมี parse_time_flexible อยู่แล้ว)
        start_time = parse_time_flexible(data.get("start_time_activity"), "08:00")
        stop_time  = parse_time_flexible(data.get("stop_time_activity"),  "09:00")

        # guard: stop ต้อง > start
        if not (start_time and stop_time) or not (stop_time > start_time):
            return JsonResponse(
                {"status": "error", "message": "เวลาเริ่ม/สิ้นสุดไม่ถูกต้อง"},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # 1) ชื่อห้ามซ้ำ
        if WeekActivity.objects.filter(act_name_activity=name, created_by=request.user).exists():
            return JsonResponse(
                {"status": "error", "message": "ชื่อกิจกรรมนี้ถูกใช้แล้ว กรุณาใช้ชื่ออื่น"},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # 2) ห้ามทับช่วงเวลาในวันเดียวกัน
        conflicts = _overlap_exists(day, start_time, stop_time, created_by=request.user)
        if _overlap_exists(day, start_time, stop_time, created_by=request.user):
            return JsonResponse(
        {"status": "error", "message": "เวลานี้ซ้ำกับกิจกรรมอื่น"},
        status=400, json_dumps_params={"ensure_ascii": False},
        )

        # 3) ✨ กันชนกับ PreSchedule ของ user นี้
        pre_overlap = PreSchedule.objects.filter(
            created_by=request.user, day_pre=day
        ).filter(
            Q(start_time_pre__lt=stop_time) & Q(stop_time_pre__gt=start_time)
        ).exists()
        if pre_overlap:
            return JsonResponse(
                {"status": "error",
                 "message": (f"เวลาทับกับ 'วิชาล่วงหน้า' วัน {day} "
                             f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}")},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # ผ่านตรวจ -> สร้าง
        activity = WeekActivity.objects.create(
            act_name_activity=name,
            day_activity=day,
            hours_activity=int(data.get("hours_activity", 0)),
            start_time_activity=start_time,
            stop_time_activity=stop_time,
            created_by=request.user,   # ✅ ผูกกับ user
        )
        return JsonResponse(
            {"status": "success", "message": "เพิ่มกิจกรรมสำเร็จ", "activity_id": activity.id},
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        logger.error(f"Error adding activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500, json_dumps_params={"ensure_ascii": False},
        )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def add_activity_bulk(request):
    """API สำหรับเพิ่มกิจกรรมหลายรายการพร้อมกัน"""
    try:
        data = json.loads(request.body or "{}")
        activities_data = data.get("activity", [])

        created_ids = []
        for row in activities_data:
            name = (row.get("act_name_activity") or "").strip()
            day = (row.get("day_activity") or "").strip()

            start_time = parse_time_flexible(row.get("start_time_activity"), "08:00")
            stop_time = parse_time_flexible(row.get("stop_time_activity"), "09:00")

            if not (name and day and start_time and stop_time and stop_time > start_time):
                continue  # skip record ที่ไม่ valid

            # กันซ้ำใน user นี้
            if WeekActivity.objects.filter(act_name_activity=name, created_by=request.user).exists():
                continue
            if _overlap_exists(day, start_time, stop_time, created_by=request.user):
                return JsonResponse({"status": "error", "message": "เวลานี้ซ้ำกับกิจกรรมอื่น"})

            pre_overlap = PreSchedule.objects.filter(
                created_by=request.user, day_pre=day
            ).filter(
                Q(start_time_pre__lt=stop_time) & Q(stop_time_pre__gt=start_time)
            ).exists()
            if pre_overlap:
                continue

            act = WeekActivity.objects.create(
                act_name_activity=name,
                day_activity=day,
                hours_activity=int(row.get("hours_activity") or 0),
                start_time_activity=start_time,
                stop_time_activity=stop_time,
                created_by=request.user,
            )
            created_ids.append(act.id)

        return JsonResponse(
            {"status": "success", "message": f"เพิ่ม {len(created_ids)} รายการสำเร็จ", "created_ids": created_ids},
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error bulk adding activity: {e}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500),

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def update_activity(request, id):
    """API สำหรับแก้ไขกิจกรรม (กันชื่อซ้ำ + กันเวลาทับในวันเดียวกัน)"""
    try:
        activity = WeekActivity.objects.get(id=id, created_by=request.user)
        data = json.loads(request.body)

        name = (data.get("act_name_activity") or activity.act_name_activity).strip()
        day  = (data.get("day_activity")       or activity.day_activity).strip()

        start_time = parse_time_flexible(
            data.get("start_time_activity") or activity.start_time_activity.strftime("%H:%M"),
            "08:00"
        )
        stop_time = parse_time_flexible(
            data.get("stop_time_activity") or activity.stop_time_activity.strftime("%H:%M"),
            "09:00"
        )

        if not (start_time and stop_time) or not (stop_time > start_time):
            return JsonResponse(
                {"status": "error", "message": "เวลาเริ่ม/สิ้นสุดไม่ถูกต้อง"},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # 1) ชื่อห้ามซ้ำ (ยกเว้นตัวเอง)
        if WeekActivity.objects.filter(act_name_activity=name).exclude(id=activity.id).exists():
            return JsonResponse(
                {"status": "error", "message": "ชื่อกิจกรรมนี้ถูกใช้แล้ว กรุณาใช้ชื่ออื่น"},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # 2) ห้ามทับช่วงเวลา (ยกเว้นตัวเอง)
        conflicts = _overlap_exists(day, start_time, stop_time, exclude_id=activity.id)
        if _overlap_exists(day, start_time, stop_time, exclude_id=activity.id, created_by=request.user):
            return JsonResponse(
                {"status": "error", "message": "เวลานี้ซ้ำกับกิจกรรมอื่น"},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        pre_overlap = PreSchedule.objects.filter(
            created_by=request.user, day_pre=day
        ).filter(
            Q(start_time_pre__lt=stop_time) & Q(stop_time_pre__gt=start_time)
        ).exists()
        if pre_overlap:
            return JsonResponse(
                {"status": "error",
                 "message": (f"เวลาทับกับ 'วิชาล่วงหน้า' วัน {day} "
                             f"ช่วง {start_time.strftime('%H:%M')}-{stop_time.strftime('%H:%M')}")},
                status=400, json_dumps_params={"ensure_ascii": False},
            )

        # ผ่านตรวจ -> บันทึก
        activity.act_name_activity = name
        activity.day_activity = day
        activity.hours_activity = int(data.get("hours_activity", activity.hours_activity))
        activity.start_time_activity = start_time
        activity.stop_time_activity  = stop_time
        activity.save()

        return JsonResponse(
            {"status": "success", "message": "แก้ไขกิจกรรมสำเร็จ"},
            json_dumps_params={"ensure_ascii": False},
        )

    except WeekActivity.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลกิจกรรม"},
            status=404, json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        logger.error(f"Error updating activity: {e}")
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500, json_dumps_params={"ensure_ascii": False},
        )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def delete_activity(request, id):
    """API สำหรับลบกิจกรรม"""
    try:
        activity = WeekActivity.objects.get(id=id, created_by=request.user)
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
@login_required(login_url="/login/")
def subject(request):
    return render(request, "subject.html", {"active_tab": "subject"})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["GET", "POST"])
def subjects_collection(request):
    if request.method == "GET":
        q = (request.GET.get("q") or "").strip()
        order = (request.GET.get("order") or "-id").strip()
        try:
            limit = int(request.GET.get("limit") or 500)
            offset = int(request.GET.get("offset") or 0)
        except ValueError:
            limit, offset = 500, 0

        # ✅ ดึงเฉพาะของ user คนนี้เท่านั้น
        qs = Subject.objects.filter(created_by=request.user)
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))

        allowed = {"id", "code", "name", "-id", "-code", "-name"}
        order = order if order in allowed else "-id"
        qs = qs.order_by(order)

        if limit > 0:
            qs = qs[offset:offset + limit]

        items = list(qs.values("id", "code", "name"))
        return JsonResponse(items, safe=False, json_dumps_params={"ensure_ascii": False})

    # POST
    data = json.loads(request.body or "{}")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        return JsonResponse(
            {"message": "กรอก code และ name ให้ครบ"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )

    obj, created = Subject.objects.update_or_create(
        code=code,
        created_by=request.user,  # ✅ ผูกกับ user
        defaults={"name": name}
    )
    return JsonResponse({"id": obj.id, "created": created}, json_dumps_params={"ensure_ascii": False})
    
@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def subjects_detail(request, pk: int):
    # PUT: update by id
    if request.method == "PUT":
        try:
            obj = Subject.objects.get(pk=pk, created_by=request.user)  # ✅ ผูกกับ user
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
    deleted, _ = Subject.objects.filter(pk=pk, created_by=request.user).delete()  # ✅ filter by user
    if not deleted:
        return JsonResponse({"message": "ไม่พบรายวิชา"}, status=404)
    return JsonResponse({"deleted": True})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def subject_delete_all(request):
    try:
        deleted_count, _ = Subject.objects.filter(created_by=request.user).delete()  # ✅ delete ของ user เท่านั้น
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
@login_required(login_url="/login/")
def teacher(request):
    return render(request, "teacher.html", {"active_tab": "teacher"})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def teacher_list(request):
    qs = Teacher.objects.filter(created_by=request.user).order_by("id")   # ✅ filter by user
    items = [{"id": t.id, "name": t.name} for t in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )

# ---------- Teacher: ADD ----------
@login_required(login_url="/login/")
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
    if Teacher.objects.filter(name__iexact=name, created_by=request.user).exists():
        return JsonResponse(
            {"status": "error", "message": "มีชื่ออาจารย์นี้อยู่แล้ว"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    t = Teacher.objects.create(name=name, created_by=request.user)  # ✅ ผูกกับ user
    return JsonResponse(
        {"status": "success", "id": t.id, "name": t.name},
        json_dumps_params={"ensure_ascii": False},
    )

# ---------- Teacher: UPDATE ----------
@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def teacher_update(request, pk):
    # หาเรคคอร์ด
    try:
        t = Teacher.objects.get(pk=pk, created_by=request.user)  # ✅ filter by user
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
    if Teacher.objects.filter(name__iexact=name, created_by=request.user).exclude(pk=pk).exists():
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def teacher_delete_all(request):
    try:
        deleted_count, _ = Teacher.objects.filter(created_by=request.user).delete()   # ✅ ของ user เท่านั้น
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def teacher_delete(request, pk):
    Teacher.objects.filter(pk=pk, created_by=request.user).delete()
    return JsonResponse({"status": "success"})

# ========== Student Group ==========
@login_required(login_url="/login/")
def studentgroup(request):
    return render(request, "studentgroup.html", {"active_tab": "studentgroup"})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def studentgroup_list(request):
    order_param = (request.GET.get("order") or "").strip()
    allowed = {"id", "name"}
    order_fields = []
    if order_param:
        for p in order_param.split(","):
            f = p.strip()
            if f.lstrip("-") in allowed:
                order_fields.append(f)
    if not order_fields:
        order_fields = ["id"]  # ค่าปริยาย

    qs = StudentGroup.objects.filter(created_by=request.user).select_related("group_type").order_by(*order_fields)
    items = [{
        "id": sg.id,
        "name": sg.name,
        "type": sg.group_type_id,
        "type_name": sg.group_type.name if sg.group_type_id else "",
    } for sg in qs]
    return JsonResponse({"status": "success", "items": items},
                        json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def studentgroup_add(request):
    data = json.loads(request.body or "{}")
    name = (data.get("name") or "").strip()
    type_id = data.get("type")

    if not name or not type_id:
        return JsonResponse({"status":"error","message":"name และ type ห้ามว่าง"},
                            status=400, json_dumps_params={"ensure_ascii": False})
    if not GroupType.objects.filter(pk=type_id).exists():
        return JsonResponse({"status":"error","message":"ไม่พบประเภทนักศึกษาที่เลือก"},
                            status=400, json_dumps_params={"ensure_ascii": False})
    # กันชื่อซ้ำ (ไม่สนตัวพิมพ์เล็กใหญ่)
    if StudentGroup.objects.filter(name__iexact=name, created_by=request.user).exists():
        return JsonResponse({"status":"error","message":f'ชื่อกลุ่ม "{name}" มีอยู่แล้ว'},
                            status=400, json_dumps_params={"ensure_ascii": False})

    sg = StudentGroup.objects.create(name=name, group_type_id=type_id, created_by=request.user)
    return JsonResponse({"status":"success",
                         "item":{"id": sg.id, "name": sg.name,
                                 "type": sg.group_type_id,
                                 "type_name": sg.group_type.name if sg.group_type_id else ""}},
                        json_dumps_params={"ensure_ascii": False})

# views.py
@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def studentgroup_update(request, pk):
    """
    อัปเดตข้อมูลกลุ่มนักศึกษา
    body: { "name": "...", "type": <group_type_id> }
    """
    try:
        sg = StudentGroup.objects.select_related("group_type").get(pk=pk, created_by=request.user)
    except StudentGroup.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลกลุ่มนักศึกษา"},
            status=404, json_dumps_params={"ensure_ascii": False}
        )

    try:
        data = json.loads(request.body or "{}")
        name = (data.get("name") or "").strip()

        # รองรับชื่อฟิลด์ทั้ง "type" และ "group_type" เผื่อหน้าบางที่ส่งมาไม่ตรงกัน
        type_id = data.get("type", data.get("group_type"))

        if not name or not type_id:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุชื่อกลุ่มและประเภทนักศึกษา"},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        # ตรวจว่า group type มีจริงไหม
        try:
            gt = GroupType.objects.get(pk=type_id, created_by=request.user)  # ✅ filter by user
        except GroupType.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "ไม่พบประเภทนักศึกษาที่เลือก"},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        # กันชื่อซ้ำ (ไม่สนตัวพิมพ์เล็ก/ใหญ่) โดยไม่ชนกับตัวเอง
        if StudentGroup.objects.filter(name__iexact=name, created_by=request.user).exclude(id=pk).exists():
            return JsonResponse(
                {"status": "error", "message": f'ชื่อกลุ่ม "{name}" มีอยู่แล้ว'},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        # อัปเดต
        sg.name = name
        sg.group_type_id = gt.id
        sg.save()

        return JsonResponse(
            {
                "status": "success",
                "message": "แก้ไขข้อมูลสำเร็จ",
                "item": {
                    "id": sg.id,
                    "name": sg.name,
                    "type": sg.group_type_id,
                    "type_name": sg.group_type.name if sg.group_type_id else "",
                },
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500, json_dumps_params={"ensure_ascii": False}
        )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def studentgroup_delete(request, pk):
    StudentGroup.objects.filter(pk=pk, created_by=request.user).delete()
    return JsonResponse({"status": "success"})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def studentgroup_delete_all(request):
    try:
        deleted_count, _ = StudentGroup.objects.filter(created_by=request.user).delete()   # ✅ ของ user เท่านั้น
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
@login_required(login_url="/login/")
def grouptype(request):
    return render(request, "grouptype.html", {"active_tab": "grouptype"})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def grouptype_list(request):
    qs = GroupType.objects.filter(created_by=request.user).order_by("id")  # ✅ filter by user
    items = [{"id": x.id, "type": x.name} for x in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def grouptype_add(request):
    """
    เพิ่มประเภทนักศึกษา โดยไม่ต้องส่ง id (ปล่อยให้ DB auto)
    body: { "type": "<ชื่อประเภท>" }
    """
    try:
        data = json.loads(request.body or "{}")
        name = (data.get("type") or "").strip()
        if not name:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุชื่อประเภทนักศึกษา"},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        # กันชื่อซ้ำ (ไม่สนตัวพิมพ์เล็กใหญ่)
        if GroupType.objects.filter(name__iexact=name, created_by=request.user).exists():
            return JsonResponse(
                {"status": "error", "message": f'ชื่อ "{name}" มีอยู่แล้ว'},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        gt = GroupType.objects.create(name=name, created_by=request.user)  # <-- ไม่ส่ง id
        return JsonResponse(
            {"status": "success", "message": "เพิ่มข้อมูลสำเร็จ", "item": {"id": gt.id, "type": gt.name}},
            json_dumps_params={"ensure_ascii": False}
        )
    except IntegrityError:
        return JsonResponse(
            {"status": "error", "message": "ชื่อซ้ำในระบบ"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500, json_dumps_params={"ensure_ascii": False}
        )

# --- GroupType update ---
@csrf_exempt
@require_http_methods(["PUT"])
def grouptype_update(request, pk):
    """
    อัปเดตชื่อประเภทนักศึกษา (type) — ห้ามซ้ำ, ห้ามว่าง
    """
    import json
    try:
        gt = GroupType.objects.get(id=pk, created_by=request.user)  # ✅ filter by user
    except GroupType.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบข้อมูลประเภทนักศึกษา"},
            status=404, json_dumps_params={"ensure_ascii": False}
        )

    try:
        data = json.loads(request.body or "{}")
        new_name = (data.get("type") or "").strip()
        if not new_name:
            return JsonResponse(
                {"status": "error", "message": "กรุณาระบุชื่อประเภทนักศึกษา"},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        # unique โดยโมเดลบังคับอยู่แล้ว แต่กันซ้ำล่วงหน้าให้ด้วย
        if GroupType.objects.filter(name=new_name, created_by=request.user).exclude(id=pk).exists():
            return JsonResponse(
                {"status": "error", "message": f'ชื่อ "{new_name}" มีอยู่แล้ว'},
                status=400, json_dumps_params={"ensure_ascii": False}
            )

        gt.name = new_name
        gt.save()
        return JsonResponse(
            {"status": "success", "message": "แก้ไขข้อมูลสำเร็จ"},
            json_dumps_params={"ensure_ascii": False}
        )
    except IntegrityError:
        return JsonResponse(
            {"status": "error", "message": "ชื่อซ้ำในระบบ"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=500, json_dumps_params={"ensure_ascii": False}
        )
    
@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def grouptype_delete(request, pk):
    try:
        gt = GroupType.objects.get(pk=pk, created_by=request.user)  # ✅ filter by user
        # อาจเจอ ProtectedError ถ้ามี StudentGroup อ้างอิงอยู่
        gt.delete()
        return JsonResponse({"status": "success", "message": "ลบสำเร็จ"})
    except ProtectedError:
        return JsonResponse({
            "status": "error",
            "message": "ไม่สามารถลบได้: มีข้อมูลกลุ่มนักศึกษาที่อ้างอิงประเภทนี้อยู่"
        }, status=400)
    except GroupType.DoesNotExist:
        return JsonResponse({"status": "error", "message": "ไม่พบรายการ"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"{e}"}, status=500)

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def grouptype_delete_all(request):
    try:
        # อาจเจอ ProtectedError ถ้ามี StudentGroup อ้างอิงอยู่
        deleted, _ = GroupType.objects.filter(created_by=request.user).delete()  # ✅ ของ user เท่านั้น
        return JsonResponse({
            "status": "success",
            "message": f"ลบทั้งหมดสำเร็จ ({deleted} รายการ)",
            "deleted_count": deleted
        })
    except ProtectedError:
        return JsonResponse({
            "status": "error",
            "message": "ไม่สามารถลบทั้งหมดได้: มีรายการที่ถูกอ้างอิงโดยกลุ่มนักศึกษา"
        }, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"{e}"}, status=500)


# ========== Group Allow ==========
@login_required(login_url="/login/")
def groupallow(request):
    return render(request, "groupallow.html", {"active_tab": "groupallow"})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def groupallow_list(request):
    qs = GroupAllow.objects.filter(created_by=request.user).select_related("group_type", "slot").order_by("id")
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

@login_required(login_url="/login/")
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
        created_by=request.user  # ✅ ผูกกับ user
    )
    return JsonResponse(
        {"status": "success", "id": obj.id, "created": created},
        json_dumps_params={"ensure_ascii": False},
    )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def groupallow_update(request, pk):
    """
    อัปเดตคู่ (dept, slot) ของ GroupAllow id=pk
    - ป้องกันซ้ำตาม unique_together (group_type, slot)
    """
    try:
        data = json.loads(request.body or "{}")
        group_type_id = data.get("dept")
        slot_id = data.get("slot")

        if not group_type_id or not slot_id:
            return JsonResponse(
                {"status": "error", "message": "dept และ slot ห้ามว่าง"}, status=400
            )

        # ถ้า target pair มีของคนอื่นอยู่แล้ว -> แจ้งซ้ำ
        exists = GroupAllow.objects.filter(
            group_type_id=group_type_id, slot_id=slot_id, created_by=request.user
        ).exclude(pk=pk).exists()
        if exists:
            return JsonResponse(
                {"status": "error", "message": "มีคู่นี้อยู่แล้ว (ซ้ำ)"}, status=400
            )

        ga = GroupAllow.objects.get(pk=pk, created_by=request.user)
        ga.group_type_id = group_type_id
        ga.slot_id = slot_id
        ga.save(update_fields=["group_type_id", "slot_id"])

        return JsonResponse(
            {"status": "success", "id": ga.id}, json_dumps_params={"ensure_ascii": False}
        )
    except GroupAllow.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "ไม่พบรายการที่ต้องการแก้ไข"}, status=404
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": f"เกิดข้อผิดพลาด: {e}"}, status=500
        )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def groupallow_delete(request, pk):
    GroupAllow.objects.filter(pk=pk, created_by=request.user).delete()
    return JsonResponse({"status": "success"})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def groupallow_delete_all(request):
    """API สำหรับลบ GroupAllow ทั้งหมด"""
    try:
        deleted_count, _ = GroupAllow.objects.filter(created_by=request.user).delete()
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
@login_required(login_url="/login/")
def room(request):
    return render(request, "room.html", {"active_tab": "room"})


@require_http_methods(["GET"])
def room_list(request):
    qs = Room.objects.filter(created_by=request.user).select_related("room_type").order_by("id")
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

@login_required(login_url="/login/")
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
            id=rid, 
            created_by=request.user,  # ✅ กันไม่ให้แก้ของคนอื่น
            defaults={"name": name, "room_type_id": type_id}
        )
    else:
        if Room.objects.filter(name__iexact=name, created_by=request.user).exists():
            return JsonResponse(
                {"status": "error", "message": f'ห้อง "{name}" มีอยู่แล้ว'},
                status=400
            )
        obj = Room.objects.create(
            name=name,
            room_type_id=type_id,
            created_by=request.user   # ✅ บันทึกว่าเป็นของ user ไหน
        )

    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def room_delete_all(request):
    """ลบห้องเรียนทั้งหมด"""
    try:
        deleted_count, _ = Room.objects.filter(created_by=request.user).delete()
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def room_delete(request, pk):
    Room.objects.filter(pk=pk, created_by=request.user).delete()
    return JsonResponse({"status": "success"})

# ========== Rooom Type ==========
@login_required(login_url="/login/")
def roomtype(request):
    return render(request, "roomtype.html", {"active_tab": "roomtype"})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def roomtype_list(request):
    qs = RoomType.objects.filter(created_by=request.user).order_by("id")
    items = [{"id": x.id, "name": x.name} for x in qs]
    return JsonResponse(
        {"status": "success", "items": items}, json_dumps_params={"ensure_ascii": False}
    )

@login_required(login_url="/login/")
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
            id=pk, defaults={"name": name}, created_by=request.user,  # ✅ กัน user อื่น
        )
    else:
        obj = RoomType.objects.create(name=name, created_by=request.user)  # ✅ ผูกกับ user

    return JsonResponse(
        {"status": "success", "id": obj.id}, json_dumps_params={"ensure_ascii": False}
    )

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def roomtype_delete_all(request):
    """API สำหรับลบ RoomType ทั้งหมด"""
    try:
        # ตรวจว่ามีห้องที่อ้างอิงอยู่ไหม
        if Room.objects.filter(created_by=request.user).exists():
            return JsonResponse({
                "status": "error",
                "message": "ไม่สามารถลบได้: มีห้องที่ยังใช้ประเภทห้องนี้อยู่"
            }, status=400, json_dumps_params={"ensure_ascii": False})

        deleted_count, _ = RoomType.objects.filter(created_by=request.user).delete()
        return JsonResponse({
            "status": "success",
            "message": f"ลบ RoomType ทั้งหมดสำเร็จ ({deleted_count} รายการ)",
            "deleted_count": deleted_count
        }, json_dumps_params={"ensure_ascii": False})

    except ProtectedError:
        return JsonResponse({
            "status": "error",
            "message": "ไม่สามารถลบได้: มีห้องที่ยังอ้างอิงประเภทนี้อยู่"
        }, status=400, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาดในการลบทั้งหมด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def roomtype_delete(request, pk):
    """API สำหรับลบประเภทห้อง (ตรวจว่ามีห้องอ้างอิงอยู่หรือไม่)"""
    try:
        # ตรวจว่ามี Room ที่อ้างอิงอยู่ไหม
        if Room.objects.filter(room_type_id=pk, created_by=request.user).exists():
            return JsonResponse({
                "status": "error",
                "message": "ไม่สามารถลบได้: มีห้องที่ยังใช้อยู่ในประเภทห้องนี้"
            }, status=400, json_dumps_params={"ensure_ascii": False})
        
        RoomType.objects.filter(pk=pk, created_by=request.user).delete()
        return JsonResponse({"status": "success", "message": "ลบประเภทห้องสำเร็จ"},
                            json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": f"เกิดข้อผิดพลาด: {str(e)}"
        }, status=500, json_dumps_params={"ensure_ascii": False})


# ========== Time Slot ==========
def timeslot(request):
    return render(request, "timeslot.html", {"active_tab": "timeslot"})

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

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def timeslot_list(request):
    qs = TimeSlot.objects.filter(created_by=request.user).order_by("day_of_week", "start_time")
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["POST"])
def timeslot_add(request):
    data = json.loads(request.body or "{}")
    day   = _norm_day(data.get("day"))
    start = parse_time(str(data.get("start") or "").strip())
    end   = parse_time(str(data.get("end") or "").strip())

    if not day or not start or not end:
        return JsonResponse(
            {"status": "error", "message": "กรอกวัน/เวลาให้ครบ (HH:MM)"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )
    if start >= end:
        return JsonResponse(
            {"status": "error", "message": "เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )

    # กันซ้ำ: วันเดียวกัน + เวลาเดียวกัน
    if TimeSlot.objects.filter(day_of_week=day, start_time=start, stop_time=end, created_by=request.user).exists():
        return JsonResponse(
            {"status": "error", "message": "วันเดียวกันไม่อนุญาตให้มีช่วงเวลาเดียวกันซ้ำ"},
            status=400, json_dumps_params={"ensure_ascii": False}
        )

    obj = TimeSlot.objects.create(day_of_week=day, start_time=start, stop_time=end, created_by=request.user)
    return JsonResponse({"status": "success", "id": obj.id},
                        json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["PUT"])
def timeslot_update(request, pk: int):
    """แก้ไขคาบเวลา: ใช้ id จาก URL"""
    try:
        obj = TimeSlot.objects.get(pk=pk, created_by=request.user)
    except TimeSlot.DoesNotExist:
        return JsonResponse({"status": "error", "message": "ไม่พบคาบเวลา"}, status=404)

    data  = json.loads(request.body or "{}")
    day   = (data.get("day") or obj.day_of_week)
    start = parse_time(str(data.get("start") or obj.start_time.strftime("%H:%M")))
    end   = parse_time(str(data.get("end")   or obj.stop_time.strftime("%H:%M")))

    if not day or not start or not end:
        return JsonResponse({"status":"error","message":"กรอกวัน/เวลาให้ครบ (HH:MM)"}, status=400)
    if start >= end:
        return JsonResponse({"status":"error","message":"เวลาเริ่มต้องน้อยกว่าเวลาสิ้นสุด"}, status=400)

    # กันซ้ำ (วัน+ช่วงเวลา) ยกเว้นตัวเอง
    if TimeSlot.objects.filter(day_of_week=day, start_time=start, stop_time=end, created_by=request.user).exclude(pk=pk).exists():
        return JsonResponse({"status":"error","message":"วันเดียวกันไม่อนุญาตให้มีช่วงเวลาเดียวกันซ้ำ"}, status=400)

    obj.day_of_week = day
    obj.start_time  = start
    obj.stop_time   = end
    obj.save(update_fields=["day_of_week", "start_time", "stop_time"])
    return JsonResponse({"status":"success", "id": obj.id})

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def timeslot_delete_all(request):
    try:
        deleted_count, _ = TimeSlot.objects.filter(created_by=request.user).delete()
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

@login_required(login_url="/login/")
@csrf_exempt
@require_http_methods(["DELETE"])
def timeslot_delete(request, pk):
    TimeSlot.objects.filter(pk=pk, created_by=request.user).delete()
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
@login_required(login_url="/login/")
@require_http_methods(["GET"])
def meta_days(request):
    codes = TimeSlot.objects.filter(created_by=request.user)\
                            .values_list("day_of_week", flat=True).distinct()
    days = sorted(set(codes), key=lambda c: _DAY_ORDER_THAI.get(c, 99))
    payload = [{"value": c, "text": _DAY_THAI.get(c, c)} for c in days]
    return JsonResponse({"days": payload}, json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def meta_start_times(request):
    day = _norm_day(request.GET.get("day"))
    if not day: return JsonResponse({"start_times": []}, json_dumps_params={"ensure_ascii": False})
    times = (TimeSlot.objects.filter(day_of_week=day, created_by=request.user)
             .order_by("start_time").values_list("start_time", flat=True).distinct())
    payload = [{"value": t.strftime("%H:%M"), "text": t.strftime("%H:%M")} for t in times]
    return JsonResponse({"start_times": payload}, json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def meta_stop_times(request):
    day = _norm_day(request.GET.get("day"))
    start = parse_time(str(request.GET.get("start") or "").strip())
    if not day or not start:
        return JsonResponse({"stop_times": []}, json_dumps_params={"ensure_ascii": False})
    times = (TimeSlot.objects.filter(day_of_week=day, start_time=start, created_by=request.user)
             .order_by("stop_time").values_list("stop_time", flat=True).distinct())
    payload = [{"value": t.strftime("%H:%M"), "text": t.strftime("%H:%M")} for t in times]
    return JsonResponse({"stop_times": payload}, json_dumps_params={"ensure_ascii": False})
# ========== Lookup APIs สำหรับดรอปดาวน์ ==========

# ---------------- lookups (filter by user) ----------------
@login_required(login_url="/login/")
@require_GET
def teachers_lookup(request):
    q = (request.GET.get("q") or "").strip()
    qs = Teacher.objects.filter(created_by=request.user)
    if q: qs = qs.filter(name__icontains=q)
    qs = qs.order_by("name")
    items = [{"id": t.id, "name": t.name} for t in qs[:50]]
    return JsonResponse({"status":"success","items": items},
                        json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_GET
def room_types_lookup(request):
    q = (request.GET.get("q") or "").strip()
    qs = RoomType.objects.filter(created_by=request.user)
    if q: qs = qs.filter(name__icontains=q)
    qs = qs.order_by("name")
    items = [{"id": x.id, "name": x.name} for x in qs[:50]]
    return JsonResponse({"status":"success","items": items},
                        json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_GET
def student_groups_lookup(request):
    q = (request.GET.get("q") or "").strip()
    qs = StudentGroup.objects.filter(created_by=request.user).select_related("group_type")
    if q: qs = qs.filter(name__icontains=q)
    qs = qs.order_by("name")
    items = [{"id": g.id, "name": g.name} for g in qs[:50]]
    return JsonResponse({"status":"success","items": items},
                        json_dumps_params={"ensure_ascii": False})


# ---------------- list/view entities (GA/Pre/Activity) ----------------
@login_required(login_url="/login/")
@require_http_methods(["GET"])
def list_generated_entities_api(request):
    view = (request.GET.get("view") or "teacher").lower().strip()
    field_map = {"teacher":"teacher","room":"room",
                 "group":"student_group","student_group":"student_group",
                 "students":"student_group","student":"student_group"}
    field = field_map.get(view, "teacher")
    q = (request.GET.get("q") or "").strip()

    qs = GeneratedSchedule.objects.filter(created_by=request.user)
    if q: qs = qs.filter(**{f"{field}__icontains": q})
    rows = qs.values(field).annotate(items=Count("id")).order_by(field)
    results = [{"key": r[field] or "N/A", "display": r[field] or "N/A", "count": r["items"]} for r in rows]
    return JsonResponse({"status":"success","view":view,"results":results},
                        json_dumps_params={"ensure_ascii": False})

@login_required(login_url="/login/")
@require_http_methods(["GET"])
def schedule_detail_api(request):
    """
    ?view=teacher|room|student_group  & key=<ชื่อ>
    รวมจาก GeneratedSchedule + PreSchedule (+ Activity เฉพาะ N/A)
    """
    view = (request.GET.get("view") or "teacher").lower().strip()
    key  = (request.GET.get("key") or "").strip()
    if not key:
        return JsonResponse({"status":"error","message":"missing key"}, status=400)

    field_map = {"teacher":"teacher","room":"room",
                 "group":"student_group","student_group":"student_group",
                 "students":"student_group","student":"student_group"}
    field = field_map.get(view, "teacher")

    rows = []
    gqs = (GeneratedSchedule.objects.filter(created_by=request.user)
           .filter(**{f"{field}__iexact": key}).order_by("day_of_week","start_time","id"))
    for g in gqs:
        rows.append({
            "Source":"Generated","Day":g.day_of_week or "",
            "Start": g.start_time.strftime("%H:%M") if g.start_time else "",
            "Stop":  g.stop_time.strftime("%H:%M")  if g.stop_time  else "",
            "Course_Code": g.subject_code or "",
            "Subject_Name": g.subject_name or "",
            "Teacher": g.teacher or "",
            "Room": g.room or "", "Type": g.type or "",
            "Student_Group": g.student_group or "", "Section": g.section or "",
        })

    pre_field_map = {"teacher":"teacher_name_pre", "room":"room_name_pre", "student_group":"student_group_name_pre"}
    pf = pre_field_map[field]
    pqs = (PreSchedule.objects.filter(created_by=request.user)
           .filter(**{f"{pf}__iexact": key}).order_by("day_pre","start_time_pre","id"))
    for p in pqs:
        rows.append({
            "Source":"Pre","Day":p.day_pre or "",
            "Start": p.start_time_pre.strftime("%H:%M") if p.start_time_pre else "",
            "Stop":  p.stop_time_pre.strftime("%H:%M")  if p.stop_time_pre  else "",
            "Course_Code": p.subject_code_pre or "", "Subject_Name": p.subject_name_pre or "",
            "Teacher": p.teacher_name_pre or "", "Room": p.room_name_pre or "",
            "Type": p.type_pre or p.room_type_pre or "", "Student_Group": p.student_group_name_pre or "",
            "Section": p.section_pre or "",
        })

    if key.upper() == "N/A":
        aqs = WeekActivity.objects.filter(created_by=request.user).order_by("day_activity","start_time_activity","id")
        for a in aqs:
            rows.append({
                "Source":"Activity", "Day":a.day_activity or "",
                "Start": a.start_time_activity.strftime("%H:%M") if a.start_time_activity else "",
                "Stop":  a.stop_time_activity.strftime("%H:%M")  if a.stop_time_activity  else "",
                "Course_Code":"", "Subject_Name":a.act_name_activity or "กิจกรรม",
                "Teacher":"N/A", "Room":"N/A", "Type":"activity", "Student_Group":"N/A",
            })

    _ORDER = {"จันทร์":1,"อังคาร":2,"พุธ":3,"พฤหัสบดี":4,"ศุกร์":5,"เสาร์":6,"อาทิตย์":7}
    def _key(r):
        d = _ORDER.get(r["Day"],99)
        try:
            hh,mm = (r["Start"] or "00:00").split(":")
            t = int(hh)*60 + int(mm)
        except Exception:
            t = 0
        return (d,t,r.get("Subject_Name",""))
    rows.sort(key=_key)
    return JsonResponse({"status":"success","view":view,"key":key,"rows":rows},
                        json_dumps_params={"ensure_ascii": False})
# ========== Timetable by entity (teacher/room/student_group) ==========

# === NEW: timetable by entity ===
# ลำดับวันสำหรับ sort (ไทย)
_DAY_ORDER_THAI = {"จันทร์":1,"อังคาร":2,"พุธ":3,"พฤหัสบดี":4,"ศุกร์":5,"เสาร์":6,"อาทิตย์":7}

def _fmt(t):
    return t.strftime("%H:%M") if t else ""

@require_GET
def timetable_by_entity(request):
    view = (request.GET.get("view") or "teacher").lower().strip()
    key  = (request.GET.get("key")  or "").strip()
    if not key:
        return JsonResponse({"status": "error", "message": "missing key"}, status=400)

    # ใช้ตัวรวบรวมข้อมูลแทนลูปเดิมทั้งหมด
    items = _collect_timetable_items(view, key, request.user)

    return JsonResponse(
        {"status": "success", "key": key, "view": view, "items": items},
        json_dumps_params={"ensure_ascii": False},
    )

def _lookup_section_for_ga(g):
    """พยายามหา section จาก CourseSchedule เมื่อ GeneratedSchedule.section ว่าง"""
    from .models import CourseSchedule
    qs = CourseSchedule.objects.filter(subject_code_course=g.subject_code)

    if g.teacher:
        qs = qs.filter(teacher_name_course=g.teacher)
    if g.student_group:
        qs = qs.filter(student_group_name_course=g.student_group)

    # ถ้าเหลืออันเดียวชัวร์ ๆ ก็ใช้เลย
    one = qs.first() if qs.count() == 1 else None
    if one:
        return one.section_course or ""

    # สำรอง: ถ้า filter ข้างบนไม่เหลืออันเดียว ลองใช้ตัวกรองที่อ่อนลง
    alt = CourseSchedule.objects.filter(subject_code_course=g.subject_code).first()
    return (alt.section_course if alt else "") or ""

def _collect_timetable_items(view: str, key: str, user):
    view = (view or "teacher").lower().strip()
    key  = (key or "").strip()

    results = []
    field_map = {"teacher":"teacher","room":"room","student_group":"student_group"}
    f = field_map.get(view, "teacher")
    for g in GeneratedSchedule.objects.filter(created_by=user, **{f: key}).order_by("day_of_week","start_time","id"):
        results.append({
            "Source":"GA","Day": g.day_of_week or "",
            "StartTime": g.start_time.strftime("%H:%M") if g.start_time else "",
            "StopTime":  g.stop_time.strftime("%H:%M")  if g.stop_time  else "",
            "Course_Code": g.subject_code or "", "Subject_Name": g.subject_name or "",
            "Teacher": g.teacher or "", "Room": g.room or "",
            "Type": (g.type or "").lower(), "Student_Group": g.student_group or "",
            "Section": g.section or "",
        })

    pre_field = {"teacher":"teacher_name_pre","room":"room_name_pre","student_group":"student_group_name_pre"}.get(view,"teacher_name_pre")
    for p in PreSchedule.objects.filter(created_by=user, **{pre_field: key}).order_by("day_pre","start_time_pre","id"):
        results.append({
            "Source":"PRE","Day": p.day_pre or "",
            "StartTime": p.start_time_pre.strftime("%H:%M") if p.start_time_pre else "",
            "StopTime":  p.stop_time_pre.strftime("%H:%M")  if p.stop_time_pre  else "",
            "Course_Code": p.subject_code_pre or "", "Subject_Name": p.subject_name_pre or "",
            "Teacher": p.teacher_name_pre or "", "Room": p.room_name_pre or "",
            "Type": (p.type_pre or p.room_type_pre or "").lower(),
            "Student_Group": p.student_group_name_pre or "", "Section": p.section_pre or "",
        })

    for a in WeekActivity.objects.filter(created_by=user).order_by("day_activity","start_time_activity","id"):
        results.append({
            "Source":"ACT","Day": a.day_activity or "",
            "StartTime": a.start_time_activity.strftime("%H:%M") if a.start_time_activity else "",
            "StopTime":  a.stop_time_activity.strftime("%H:%M")  if a.stop_time_activity  else "",
            "Course_Code": "", "Subject_Name": a.act_name_activity or "กิจกรรม",
            "Teacher": "N/A","Room": "N/A","Type": "activity","Student_Group": "N/A",
        })

    _ORDER = {"จันทร์":1,"อังคาร":2,"พุธ":3,"พฤหัสบดี":4,"ศุกร์":5,"เสาร์":6,"อาทิตย์":7}
    results.sort(key=lambda r: (_ORDER.get(r["Day"],99), r["StartTime"] or "99:99", r["Subject_Name"]))
    return results

# ---------- แกนกลาง: ดึงข้อมูล "เหมือนในตารางโมดัล" ----------
def _get_items_for_entity(view: str, key: str):
    return _collect_timetable_items(view, key, request.user)

# ---------- จัด block ต่อเนื่อง & เตรียม grid ----------
TT_DAY_ORDER = ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์","เสาร์","อาทิตย์"]
TT_START = (8, 0)    # 08:00
TT_END   = (21, 0)   # 21:00
TT_SLOT_MIN = 30     # นาทีต่อคอลัมน์

def _tmin(hhmm: str) -> int:
    if not hhmm: return None
    hh, mm = hhmm.split(":")
    return int(hh)*60 + int(mm)

def _min_to_label(m):
    h, mm = divmod(m, 60)
    return f"{h:02d}.{mm:02d}"

def _label_lines(r: dict) -> list[str]:
    """
    ทำข้อความสั้นๆ เป็นบรรทัด (แบบรูปตัวอย่าง)
    1) รหัสวิชา (หรือ Subject_Name ถ้าไม่มีรหัส)
    2) section ถ้ามี
    3) ห้อง ถ้ามี
    """
    code = (r.get("Course_Code") or "").strip()
    subj = (r.get("Subject_Name") or "").strip()
    sec  = (r.get("Section") or "").strip()
    room = (r.get("Room") or "").strip()

    head = code or subj or "-"
    lines = [head]
    if sec:  lines.append(sec)
    if room: lines.append(room)
    return lines

def _build_grid(items):
    """
    รวมบล็อกที่ 'ทับกัน' ในวันเดียวกันให้เป็นกล่องเดียว
    - ถ้าทับกัน: รวมช่วงเวลาเป็น union และสะสมข้อความหลายรายการเป็นหลายบรรทัด
    - ถ้าต่อเนื่องกันแบบวิชาเดียวกัน: merge ต่อเนื่องเหมือนเดิม
    """
    start_min = TT_START[0]*60 + TT_START[1]
    end_min   = TT_END[0]*60 + TT_END[1]
    slots = (end_min - start_min)//TT_SLOT_MIN

    def _tmin(hhmm: str|None):
        if not hhmm: return None
        hh, mm = hhmm.split(":")
        return int(hh)*60+int(mm)

    # สร้างรายการบล็อกดิบ (แปลงเป็น index ของคาบครึ่งชั่วโมง)
    raw_by_day: dict[str, list[dict]] = {d: [] for d in TT_DAY_ORDER}
    for r in items:
        day = r.get("Day") or ""
        if day not in raw_by_day: 
            continue
        s = _tmin(r.get("StartTime"))
        e = _tmin(r.get("StopTime"))
        if s is None or e is None or e <= s:
            continue
        s = max(start_min, min(s, end_min))
        e = max(start_min, min(e, end_min))
        sh = (s - start_min) // TT_SLOT_MIN
        eh = (e - start_min + TT_SLOT_MIN - 1) // TT_SLOT_MIN
        sh = max(0, min(sh, slots))
        eh = max(0, min(eh, slots))
        if eh <= sh:
            continue

        raw_by_day[day].append({
            "sh": sh, "eh": eh,
            "Type": (r.get("Type") or "").lower(),
            "lines": _label_lines(r),  # เก็บข้อความไว้เป็น list ของบรรทัด
            # เก็บต้นฉบับเผื่ออยากใช้ tooltip ในอนาคต
            "_raw": r,
        })

    # ขั้นตอน merge
    merged_by_day: dict[str, list[dict]] = {}
    for d, xs in raw_by_day.items():
        xs = sorted(xs, key=lambda x: x["sh"])
        out: list[dict] = []

        for b in xs:
            if not out:
                out.append({**b})
                continue

            cur = out[-1]
            # 1) ถ้าวิชาเดียวกันต่อเนื่อง (บรรทัดเหมือนกันทุกบรรทัดและชนิดเดียวกัน) → ต่อช่วงเวลา
            same_subject = (cur["lines"] == b["lines"] and cur["Type"] == b["Type"])
            if same_subject and b["sh"] <= cur["eh"]:
                cur["eh"] = max(cur["eh"], b["eh"])
                continue

            # 2) ถ้าทับช่วงเวลา (ชนกัน) → รวมเป็นกล่องเดียว (union) และต่อบรรทัดเข้าไป
            overlap = b["sh"] < out[-1]["eh"]
            if overlap:
                cur["eh"] = max(cur["eh"], b["eh"])
                # ต่อข้อความแบบไม่ซ้ำบรรทัดหัว
                for ln in b["lines"]:
                    if ln not in cur["lines"]:
                        cur["lines"].append(ln)
                # ถ้าประเภทใดเป็น activity ให้ถือว่าเป็น activity (เพื่อทำสี)
                if "activity" in (cur["Type"], b["Type"]):
                    cur["Type"] = "activity"
                continue

            # 3) ไม่ทับ → เริ่มกล่องใหม่
            out.append({**b})

        merged_by_day[d] = out

    # ป้ายหัวคอลัมน์เวลา (08.00-08.30, ...)
    labels = []
    for i in range(slots):
        s = start_min + i*TT_SLOT_MIN
        e = s + TT_SLOT_MIN
        hs, ms = divmod(s, 60)
        he, me = divmod(e, 60)
        labels.append(f"{hs:02d}.{ms:02d}-{he:02d}.{me:02d}")

    return {
        "slots": slots,
        "slot_labels": labels,
        "blocks_by_day": merged_by_day,
    }

def _phase_label(t: str) -> str:
    t = (t or "").lower()
    if t == "lab":
        return "lab (ปฏิบัติ)"
    if t == "theory":
        return "theory (ทฤษฎี)"
    if t == "activity":
        return "กิจกรรม"
    return ""

# === SUMMARY TABLE (no credits) =====================

def _mins(hhmm: str) -> int:
    if not hhmm: return 0
    try:
        hh, mm = hhmm.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return 0

def _aggregate_detail(items: list[dict]) -> dict:
    """
    รวมแถว items (จาก _collect_timetable_items) ให้ได้สรุปต่อรายวิชา/section
    คืน dict: { "rows": [...], "totals": {...} }
    """
    groups = {}  # key = (code, section or student_group)
    for r in items:
        if r.get("Type", "").lower() == "activity":
            # กิจกรรมไม่ขึ้นในตารางสรุปรายวิชา
            continue

        code = (r.get("Course_Code") or "").strip()
        name = (r.get("Subject_Name") or "").strip()
        # ใช้ Section ถ้ามี; ถ้าไม่มีใช้ Student_Group; ถ้ายังไม่มีให้ "-"
        sec_or_group = (r.get("Section") or r.get("Student_Group") or "-").strip()
        typ = (r.get("Type") or "").lower()

        s = _mins(r.get("StartTime") or "")
        e = _mins(r.get("StopTime") or "")
        dur = max(0, e - s)

        key = (code, sec_or_group)
        g = groups.setdefault(key, {
            "course_code": code,
            "subject_name": name,
            "group": sec_or_group,
            "hours_theory_min": 0,
            "hours_lab_min": 0,
            "hours_total_min": 0,
        })
        if "lab" in typ:
            g["hours_lab_min"] += dur
        else:
            g["hours_theory_min"] += dur
        g["hours_total_min"] += dur

    def to_hr(m):  # นาที -> ชั่วโมงทศนิยม 1 ตำแหน่ง
        return round(m / 60.0, 1)

    rows = []
    tot_t, tot_l, tot_all = 0, 0, 0
    idx = 1
    for (_code, _grp), g in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        t = g["hours_theory_min"]; l = g["hours_lab_min"]; a = g["hours_total_min"]
        rows.append({
            "no": idx,
            "course_code": g["course_code"],
            "subject_name": g["subject_name"],
            "group": g["group"],       # ใช้แทน “กลุ่มเรียน”
            "hours_t": to_hr(t),
            "hours_l": to_hr(l),
            "hours_sum": to_hr(a),
        })
        idx += 1
        tot_t += t; tot_l += l; tot_all += a

    totals = {"hours_t": to_hr(tot_t), "hours_l": to_hr(tot_l), "hours_sum": to_hr(tot_all)}
    return {"rows": rows, "totals": totals}

# ---- ช่วยแปลงเวลา HH:MM -> นาที ----
def _tmin_str(s: str) -> int | None:
    try:
        hh, mm = str(s or "00:00").split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return None

def _overlap_time(a_s: str, a_e: str, b_s: str, b_e: str) -> bool:
    """ทับช่วงมาตรฐาน: new_start < old_stop และ new_stop > old_start"""
    a1, a2 = _tmin_str(a_s), _tmin_str(a_e)
    b1, b2 = _tmin_str(b_s), _tmin_str(b_e)
    if None in (a1, a2, b1, b2):
        return False
    return (a1 < b2) and (a2 > b1)

def _filter_pre_overlaps(items):
    ga = [x for x in items if (x.get("Source") or "").upper() in {"GA","GENERATED"}]
    out = []
    def _mins(s):
        try: hh,mm = str(s or "00:00").split(":"); return int(hh)*60+int(mm)
        except Exception: return None
    for r in items:
        if (r.get("Source") or "").upper() != "PRE":
            out.append(r); continue
        day = r.get("Day",""); keep = True
        rs, re = _mins(r.get("StartTime")), _mins(r.get("StopTime"))
        for g in ga:
            if g.get("Day","") != day: continue
            gs, ge = _mins(g.get("StartTime")), _mins(g.get("StopTime"))
            if None in (rs,re,gs,ge): continue
            if rs < ge and re > gs:
                keep = False; break
        if keep: out.append(r)
    return out

def _build_cells_for_day(blocks: list[dict], slots: int) -> list[dict]:
    """
    แปลงบล็อกที่ merge แล้วเป็น cells ให้ template ใช้
    - ใส่ html (หลายบรรทัด) ให้พร้อมเรนเดอร์
    """
    bs = sorted(blocks, key=lambda x: x["sh"])
    out = []
    idx = 0
    i = 0
    while idx < slots:
        # เริ่มกล่องที่ column นี้พอดี
        if i < len(bs) and bs[i]["sh"] == idx:
            b = bs[i]
            span = max(1, b["eh"] - b["sh"])
            html = "<br>".join([str(x) for x in b.get("lines", [])]) or "&nbsp;"
            out.append({
                "render": True,
                "colspan": span,
                "block": {
                    "html": html,
                    "type": (b.get("Type") or ""),
                    "phase_label": _phase_label(b.get("Type"))
                }
            })
            idx += span
            i += 1
            continue

        # ถ้าอยู่ภายในช่วงของกล่องก่อนหน้า → ข้ามช่อง
        inside = any(b["sh"] < idx < b["eh"] for b in bs[i:])
        if inside:
            idx += 1
            continue

        # ช่องว่าง
        out.append({"render": True})
        idx += 1

    return out

# --- NEW: make summary rows for bottom table in PDF ---
def _build_summary_rows(items: list[dict]) -> list[dict]:
    """
    รวมแถวซ้ำให้เหลือ 1 รายการต่อ (รหัสวิชา, ชื่อวิชา, ภาค, กลุ่ม, เซคชัน)
    ใช้ข้อมูลเดียวกับหน้าเว็บ => จะตรงกัน
    """
    seen = set()
    rows = []
    for r in items:
        code   = (r.get("Course_Code")   or "").strip()
        name   = (r.get("Subject_Name")  or "").strip()
        phase  = (r.get("Type")          or "").strip().lower()  # "theory"/"lab"/"activity"
        group  = (r.get("Student_Group") or "").strip()
        sect   = (r.get("Section")       or "").strip()

        # ปัด label ให้สวย
        if phase == "theory": phase = "ทฤษฎี"
        elif phase == "lab":  phase = "ปฏิบัติ"
        elif phase == "activity": phase = "กิจกรรม"

        key = (code, name, phase, group, sect)
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "code": code,
            "name": name,
            "phase": phase,
            "group": group or "-",
            "section": sect or "-",
        })

    # เรียงเพื่ออ่านง่าย
    rows.sort(key=lambda x: (x["code"], x["section"], x["group"], x["phase"]))
    # เติมลำดับ
    for i, r in enumerate(rows, 1):
        r["idx"] = i
    return rows

# ---------- เรนเดอร์ HTML -> PDF ----------
def _render_pdf_html(context: dict) -> bytes:
    
    html = render_to_string("timetable_pdf.html", context)

    try:
        import pdfkit
    except Exception as e:
        logger.exception("pdfkit import failed")
        raise RuntimeError(f"pdfkit import failed: {e}") from e

    options = {
        "encoding": "UTF-8",
        "page-size": "A4",
        "orientation": "Landscape",
        "margin-top": "14mm",
        "margin-right": "12mm",
        "margin-bottom": "14mm",
        "margin-left": "12mm",
        "enable-local-file-access": None,
        "quiet": "",
        "grayscale": "",
    }
    
    config = None
    wkhtml = getattr(settings, "WKHTMLTOPDF_CMD", None)
    if wkhtml:
        config = pdfkit.configuration(wkhtmltopdf=wkhtml)

    try:
        # False => คืนค่าเป็น bytes
        pdf_bytes = pdfkit.from_string(html, False, options=options, configuration=config)
        return pdf_bytes
    except Exception as e:
        logger.exception("pdfkit render failed")
        raise RuntimeError(f"wkhtmltopdf render failed: {e}") from e

# ---------- สร้างชื่อไฟล์สวย ๆ ----------
def _safe_filename(s: str) -> str:
    return re.sub(r'[\\/*?:"<>|]+', "_", s).strip() or "file"

# ---------- 1) PDF เดี่ยว ----------
@login_required(login_url="/login/")
@require_http_methods(["GET"])
def export_pdf_single(request):
    view = (request.GET.get("view") or "teacher").lower().strip()
    key  = (request.GET.get("key") or "").strip()
    if not key:
        return JsonResponse({"status":"error","message":"missing key"}, status=400,
                            json_dumps_params={"ensure_ascii": False})

    items = _collect_timetable_items(view, key, request.user)
    items = _filter_pre_overlaps(items)
    grid  = _build_grid(items)

    days_ctx = []
    for d in TT_DAY_ORDER:
        blocks = grid["blocks_by_day"].get(d, [])
        cells  = _build_cells_for_day(blocks, grid["slots"])
        days_ctx.append({"name": d, "cells": cells})

    summary_rows = _build_summary_rows(items)
    aggr = _aggregate_detail(items)

    ctx = {
        "title": f"ตารางสอน - {key}",
        "view": view, "entity_name": key,
        "slot_labels": grid["slot_labels"], "slots": range(grid["slots"]),
        "days": days_ctx,
        "summary_rows": summary_rows,
        "detail_rows": aggr["rows"], "detail_totals": aggr["totals"],
    }
    pdf_bytes = _render_pdf_html(ctx)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{_safe_filename(key)}.pdf"'
    return resp


# ---------- 2) PDF หลายไฟล์ (ZIP) ----------
@login_required(login_url="/login/")
@require_http_methods(["POST"])
def export_pdf_batch(request):
    try:
        data = json.loads(request.body or "{}")
        view = (data.get("view") or "teacher").lower().strip()
        keys = [k for k in (data.get("keys") or []) if str(k).strip()]
        if not keys:
            return JsonResponse({"status":"error","message":"no keys"}, status=400,
                                json_dumps_params={"ensure_ascii": False})

        mem = BytesIO()
        with ZipFile(mem, "w", ZIP_DEFLATED) as zf:
            for key in keys:
                items = _collect_timetable_items(view, key, request.user)
                items = _filter_pre_overlaps(items)
                grid  = _build_grid(items)

                days_ctx = []
                for d in TT_DAY_ORDER:
                    blocks = grid["blocks_by_day"].get(d, [])
                    cells  = _build_cells_for_day(blocks, grid["slots"])
                    days_ctx.append({"name": d, "cells": cells})

                summary_rows = _build_summary_rows(items)
                aggr = _aggregate_detail(items)

                ctx = {
                    "title": f"ตารางสอน - {key}",
                    "view": view, "entity_name": key,
                    "slot_labels": grid["slot_labels"], "slots": range(grid["slots"]),
                    "days": days_ctx,
                    "summary_rows": summary_rows,
                    "detail_rows": aggr["rows"], "detail_totals": aggr["totals"],
                }
                pdf = _render_pdf_html(ctx)
                zf.writestr(f"{_safe_filename(key)}.pdf", pdf)

        mem.seek(0)
        resp = HttpResponse(mem.read(), content_type="application/zip")
        resp["Content-Disposition"] = 'attachment; filename="timetables.zip"'
        return resp
    except Exception as e:
        logger.exception("export_pdf_batch error")
        return JsonResponse({"status":"error","message":str(e)}, status=500,
                            json_dumps_params={"ensure_ascii": False})
