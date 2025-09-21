from typing import List, Tuple, Dict, Any
import pandas as pd
from datetime import time
from .models import (
    CourseSchedule,
    PreSchedule,
    WeekActivity,
    Room,
    GroupAllow,
    StudentGroup,
    GeneratedSchedule,
)
import random
from collections import defaultdict

from tabulate import tabulate


def _qs_to_df(qs, fields):
    """แปลง QuerySet ของ Django → DataFrame ของ pandas"""
    return pd.DataFrame(list(qs.values(*fields)))


def fetch_all_from_db() -> Dict[str, pd.DataFrame]:
    """ดึงข้อมูลดิบทั้งหมดจากฐานข้อมูล (ยังไม่กรอง/ยังไม่ประมวลผล)"""
    courses = _qs_to_df(
        CourseSchedule.objects.all(),
        [
            "id",
            "teacher_name_course",
            "subject_code_course",
            "subject_name_course",
            "student_group_name_course",
            "room_type_course",
            "section_course",
            "theory_slot_amount_course",
            "lab_slot_amount_course",
        ],
    )

    preschedules = _qs_to_df(
        PreSchedule.objects.all(),
        [
            "id",
            "teacher_name_pre",
            "subject_code_pre",
            "subject_name_pre",
            "student_group_name_pre",
            "room_type_pre",
            "type_pre",
            "hours_pre",
            "section_pre",
            "day_pre",
            "start_time_pre",
            "stop_time_pre",
            "room_name_pre",
        ],
    )

    weekactivities = _qs_to_df(
        WeekActivity.objects.all(),
        [
            "id",
            "act_name_activity",
            "day_activity",
            "hours_activity",
            "start_time_activity",
            "stop_time_activity",
        ],
    )

    rooms = _qs_to_df(
        Room.objects.select_related("room_type"),
        ["id", "name", "room_type__name"],
    ).rename(columns={"name": "room_name", "room_type__name": "room_type"})

    groupallows = _qs_to_df(
        GroupAllow.objects.select_related("group_type", "slot"),
        [
            "id",
            "group_type__name",
            "slot__day_of_week",
            "slot__start_time",
            "slot__stop_time",
        ],
    ).rename(
        columns={
            "group_type__name": "group_type",
            "slot__day_of_week": "day_of_week",
            "slot__start_time": "start_time",
            "slot__stop_time": "stop_time",
        }
    )

    # ===== เติม group_type_id ให้ courses โดยไม่แก้สคีมา =====
    sg_df = pd.DataFrame(list(StudentGroup.objects.values("name", "group_type_id")))

    if sg_df.empty:
        courses["group_type_id"] = pd.Series(dtype="Int64")
    else:
        sg_df["name_clean"] = (
            sg_df["name"]
            .fillna("")
            .str.strip()
        )

        courses["sg_name_clean"] = (
            courses["student_group_name_course"]
            .fillna("")
            .str.strip()
        )
        # pd.set_option("display.max_rows", None)   # แสดงทุกแถว
        # pd.set_option("display.max_colwidth", None)  # ให้ข้อความยาวแค่ไหนก็แสดงครบ

        # print(sg_df["name_clean"])
        # print(courses["sg_name_clean"])
        # exit()

        courses = courses.merge(
            sg_df[["name_clean", "group_type_id"]],
            left_on="sg_name_clean",
            right_on="name_clean",
            how="left",
        )
        # .drop(columns=["name_clean", "sg_name_clean"])

        courses["group_type_id"] = courses["group_type_id"].astype("Int64")
    # ===== จบส่วนเติม group_type_id =====

    return {
        "courses": courses,
        "preschedules": preschedules,
        "weekactivities": weekactivities,
        "rooms": rooms,
        "groupallows": groupallows,
    }


# ==================== layer 1 start ==========================


def expand_weekactivities_to_slots(df_week: pd.DataFrame) -> pd.DataFrame:
    """แตก WeekActivity ออกเป็นช่วงเวลารายชั่วโมง (เช่น 15-17 → 15-16, 16-17)"""
    if df_week is None or df_week.empty:
        return pd.DataFrame(columns=["day_of_week", "start_time", "stop_time"])
    rows = []
    for _, r in df_week.iterrows():
        day_th = (r.get("day_activity") or "").strip()
        st = r.get("start_time_activity")
        et = r.get("stop_time_activity")
        if pd.isna(st) or pd.isna(et) or not st or not et:
            continue
        sh = int(getattr(st, "hour", 0))
        eh = int(getattr(et, "hour", 0))
        if eh <= sh:
            continue
        for h in range(sh, eh):
            rows.append(
                {
                    "day_of_week": day_th,
                    "start_time": time(h, 0),
                    "stop_time": time(h + 1, 0),
                }
            )
    return pd.DataFrame(rows, columns=["day_of_week", "start_time", "stop_time"])


def apply_groupallow_blocking(
    groupallows: pd.DataFrame, weekactivities: pd.DataFrame
) -> pd.DataFrame:
    """ลบช่วงเวลาของ groupallows ที่ทับกับกิจกรรมออก"""
    blocked = expand_weekactivities_to_slots(weekactivities)
    if groupallows.empty or blocked.empty:
        return groupallows
    merged = groupallows.merge(
        blocked,
        on=["day_of_week", "start_time", "stop_time"],
        how="left",
        indicator=True,
    )
    return merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])


# ==================== layer 1 end ==========================


# ==================== layer 2 start ==========================
def expand_groupallows_with_rooms(
    groupallows: pd.DataFrame, rooms: pd.DataFrame
) -> pd.DataFrame:
    """ขยาย groupallows ให้มีทุกห้อง (เพิ่มคอลัมน์ room_name) ด้วย cross join"""
    if groupallows.empty or rooms.empty:
        # คืน schema เปล่าให้แน่ใจว่าคอลัมน์ครบ
        return pd.DataFrame(
            columns=[
                "group_type",
                "day_of_week",
                "start_time",
                "stop_time",
                "room_name",
            ]
        )

    # เตรียม columns ที่ต้องใช้
    ga = groupallows[["group_type", "day_of_week", "start_time", "stop_time"]].copy()
    rm = rooms[["room_name"]].copy()

    # cross join แบบง่าย: ใส่ key=1 แล้ว merge
    ga["__key"] = 1
    rm["__key"] = 1
    out = ga.merge(rm, on="__key").drop(columns="__key")

    # จัดลำดับคอลัมน์ให้อ่านง่าย
    return out[["group_type", "day_of_week", "start_time", "stop_time", "room_name"]]


def expand_preschedules_to_slots(preschedules: pd.DataFrame) -> pd.DataFrame:
    """แตก Preschedule เป็นช่วงรายชั่วโมง + ชื่อห้อง (ไทยล้วน)"""
    if preschedules is None or preschedules.empty:
        return pd.DataFrame(
            columns=["day_of_week", "start_time", "stop_time", "room_name"]
        )

    rows = []
    for _, r in preschedules.iterrows():
        day_th = (r.get("day_pre") or "").strip()
        st = r.get("start_time_pre")
        et = r.get("stop_time_pre")
        room = (r.get("room_name_pre") or "").strip()

        if pd.isna(st) or pd.isna(et) or not st or not et or not room:
            continue

        sh = int(getattr(st, "hour", 0))
        eh = int(getattr(et, "hour", 0))
        if eh <= sh:
            continue

        for h in range(sh, eh):
            rows.append(
                {
                    "day_of_week": day_th,
                    "start_time": time(h, 0),
                    "stop_time": time(h + 1, 0),
                    "room_name": room,
                }
            )

    return pd.DataFrame(
        rows, columns=["day_of_week", "start_time", "stop_time", "room_name"]
    )


def apply_preschedule_blocking(
    ga_with_rooms: pd.DataFrame, preschedules: pd.DataFrame
) -> pd.DataFrame:
    """ลบช่วงที่ถูกจองใน preschedules (วัน/เวลา/ห้อง) ออกจาก groupallows ที่ขยายแล้ว"""
    blocked = expand_preschedules_to_slots(preschedules)
    if ga_with_rooms.empty or blocked.empty:
        return ga_with_rooms

    merged = ga_with_rooms.merge(
        blocked,
        on=["day_of_week", "start_time", "stop_time", "room_name"],
        how="left",
        indicator=True,
    )
    return merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])


# ==================== layer 2 end ==========================

# ==================== layer 3 start ========================


def explode_courses_to_units(courses: pd.DataFrame) -> pd.DataFrame:
    """
    แตกแต่ละวิชาออกเป็นหน่วยชั่วโมงตาม
    - theory_slot_amount_course  → สร้าง rows type="theory" จำนวน N แถว
    - lab_slot_amount_course     → สร้าง rows type="lab"    จำนวน M แถว

    หน่วยละ 1 ชั่วโมง (hours=1)
    """
    if courses is None or courses.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "teacher_name_course",
                "subject_code_course",
                "subject_name_course",
                "student_group_name_course",
                "room_type_course",
                "section_course",
                "type",  # "theory" / "lab"
                "hours",  # always 1
                "unit_idx",  # ลำดับชั่วโมงย่อย 1..N
                "unit_total",  # จำนวนชั่วโมงรวมของ type นั้น
            ]
        )

    rows = []
    for _, r in courses.iterrows():
        theory_n = int(r.get("theory_slot_amount_course") or 0)
        lab_n = int(r.get("lab_slot_amount_course") or 0)

        base = {
            "id": r.get("id"),
            "teacher_name_course": r.get("teacher_name_course"),
            "subject_code_course": r.get("subject_code_course"),
            "subject_name_course": r.get("subject_name_course"),
            "student_group_name_course": r.get("student_group_name_course"),
            "room_type_course": r.get("room_type_course"),
            "section_course": r.get("section_course"),
        }

        # สร้างหน่วยชั่วโมงสำหรับทฤษฎี
        for i in range(theory_n):
            rows.append(
                {
                    **base,
                    "type": "theory",
                    "hours": 1,
                    "unit_idx": i + 1,
                    "unit_total": theory_n,
                }
            )

        # สร้างหน่วยชั่วโมงสำหรับแลบ
        for i in range(lab_n):
            rows.append(
                {
                    **base,
                    "type": "lab",
                    "hours": 1,
                    "unit_idx": i + 1,
                    "unit_total": lab_n,
                }
            )

    return pd.DataFrame(rows)


# ==================== layer 3 end ==========================

# ==================== layer 4 start ==========================


def initialize_population(
    courses: pd.DataFrame,
    ga_free: pd.DataFrame,
    pop_size: int = 20,
    seed: int = 42,
):

    return population


def evaluate_individual(individual):

    return


def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame], generations: int = 100, pop_size: int = 50
):

    # คืน individual ที่ดีที่สุด
    best_fitness, best_ind = max((evaluate_individual(ind), ind) for ind in population)
    return {"fitness": best_fitness, "schedule": best_ind}


# ==================== layer 4 end ==========================
def save_ga_result(schedule_rows):
    objs = []
    for row in schedule_rows:
        objs.append(
            GeneratedSchedule(
                subject_code=row["subject_code"],
                subject_name=row["subject_name"],
                teacher=row.get("teacher"),
                student_group=row.get("student_group"),
                section=row.get("section"),
                type=row.get("type"),
                hours=row.get("hours", 0),
                day_of_week=row["day_of_week"],
                start_time=row["start_time"],
                stop_time=row["stop_time"],
                room=row.get("room"),
            )
        )
    GeneratedSchedule.objects.bulk_create(objs)


def run_genetic_algorithm_from_db() -> Dict[str, Any]:
    """ดึงข้อมูลทั้งหมด + เตรียมข้อมูลสำหรับ Genetic Algorithm (ยังไม่รันจริง)"""
    # ========= layer 1 ============
    data = fetch_all_from_db()
    data["groupallows"] = apply_groupallow_blocking(
        data["groupallows"], data["weekactivities"]
    )
    print(tabulate(data["courses"], headers="keys", tablefmt="grid", showindex=False))
    exit()
    
    # print("shape:", data["groupallows"].shape)
    # print(data["groupallows"].head(150).to_string(index=False))
    # exit()
    # ========= layer 2 ============
    ga_with_rooms = expand_groupallows_with_rooms(data["groupallows"], data["rooms"])
    ga_free = apply_preschedule_blocking(ga_with_rooms, data["preschedules"])
    data["ga_free"] = ga_free
    # print("=== ga_free ===")
    # print("shape:", ga_free.shape)
    # print(ga_free.head(100).to_string(index=False))
    # exit()
    # ========= layer 3 ============

    data["courses"] = explode_courses_to_units(data["courses"])

    # cols = [
    #     "subject_code_course",
    #     "subject_name_course",
    #     "section_course",
    #     "teacher_name_course",
    #     "student_group_name_course",
    #     "type",
    #     "unit_idx",
    #     "unit_total",
    #     "hours",
    #     "room_type_course",
    # ]
    # df = data["courses"].reindex(
    #     columns=[c for c in cols if c in data["courses"].columns]
    # )

    # pd.set_option("display.max_columns", None)
    # pd.set_option("display.max_rows", None)
    # pd.set_option("display.width", 0)  # ป้องกันตัดบรรทัดตามกว้างหน้าจอ

    # print(df.head(20).to_string(index=False))
    # exit()

    # ========= layer 4 ============
    result = run_genetic_algorithm(data, generations=100, pop_size=50)
    print("=== success ===")
    save_ga_result(result["schedule"])

    counts = {k: int(len(v)) for k, v in data.items()}
    return {
        "status": "success",
        "message": "Genetic Algorithm finished",
        "best_fitness": result["fitness"],
        "best_schedule": result["schedule"],  # ตารางที่ได้
    }
