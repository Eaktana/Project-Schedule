from typing import List, Tuple, Dict, Any
import pandas as pd
from datetime import time
from .models import (
    CourseSchedule,
    PreSchedule,
    WeekActivity,
    Room,
    GroupAllow,
    GeneratedSchedule,
)
import random


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

# ==================== optimal ga start ==========================



# ==================== optimal ga end ==========================

# ==================== layer 3 start ==========================

def initialize_population(
    courses: pd.DataFrame, ga_free: pd.DataFrame, pop_size: int = 20
):
    """สร้างประชากรเริ่มต้น (initial population)"""
    population = []
    free_slots = ga_free.to_dict(orient="records")
    for _ in range(pop_size):
        individual = []
        for _, course in courses.iterrows():
            # เลือก slot ที่ยังเหลือพอชั่วโมง
            candidate = random.choice(free_slots)
            gene = {
                "subject_code": course["subject_code_course"],
                "subject_name": course["subject_name_course"],
                "teacher": course["teacher_name_course"],
                "student_group": course["student_group_name_course"],
                "section": course["section_course"],
                "type": "theory" if course["theory_slot_amount_course"] > 0 else "lab",
                "hours": course["theory_slot_amount_course"]
                or course["lab_slot_amount_course"],
                "day_of_week": candidate["day_of_week"],
                "start_time": candidate["start_time"],
                "stop_time": candidate["stop_time"],
                "room": candidate["room_name"],
            }
            individual.append(gene)
        population.append(individual)
    return population

#======================================================================================================================
#======================================================================================================================
from collections import defaultdict
from datetime import time

# -----------------------------
# Config น้ำหนักโทษ/ค่าปรับ
# -----------------------------
WEIGHTS = {
    # Hard constraints (ต้องไม่ผิด)
    "invalid_time": 200,            # start >= stop
    "teacher_overlap": 800,         # อาจารย์ซ้อนเวลา
    "group_overlap": 800,           # กลุ่มเรียนซ้อนเวลา
    "room_overlap": 800,            # ห้องซ้อนเวลา
    "out_of_group_allow": 400,      # อยู่นอกช่วงอนุญาต
    "duration_mismatch": 250,       # (stop - start) ไม่ตรง hours
    "slot_not_aligned": 120,        # ไม่ลงล็อก 60 นาที

    # Soft constraints (เพื่อความเหมาะสม)
    "teach_too_late": 40,           # คาบที่เลย 18:00
    "teach_too_early": 30,          # คาบก่อน 09:00
    "over_lunch": 25,               # ทับช่วงพักกลางวัน (12:00-13:00)
    "daily_overload": 35,           # ชั่วโมง/วัน ของกลุ่ม > 6 ชม.
    "many_subjects_a_day": 25,      # รายวิชาต่อวันของกลุ่ม > 3
    "large_gaps": 15,               # ช่องว่างต่อวันของกลุ่ม > 120 นาที
    "teacher_same_part_of_day": 8,  # ครูทั้งสัปดาห์อยู่แต่ช่วงเวลาเดียว
    "room_building_hops": 10,       # เปลี่ยนตึกถ้าพักน้อย (<60 นาที)
}

TH_DAY = {"จันทร์":0, "อังคาร":1, "พุธ":2, "พฤหัสบดี":3, "ศุกร์":4, "เสาร์":5, "อาทิตย์":6}

def t(h, m=0):
    return time(hour=h, minute=m)

def time_to_min(ti: time) -> int:
    return ti.hour * 60 + ti.minute

def minutes_between(a: time, b: time) -> int:
    return time_to_min(b) - time_to_min(a)

def overlap_minutes(s1: time, e1: time, s2: time, e2: time) -> int:
    start = max(time_to_min(s1), time_to_min(s2))
    end   = min(time_to_min(e1), time_to_min(e2))
    return max(0, end - start)

def is_outside_allow(day_name: str, s: time, e: time, group_kind: str) -> bool:
    """
    group_kind: 'ภาคปกติ' หรือ 'ภาคพิเศษ'
    - ภาคปกติ: จันทร์–ศุกร์ 08:00–20:00
    - ภาคพิเศษ: จันทร์–ศุกร์ 08:00–20:00 + เสาร์–อาทิตย์ 08:00–20:00
    """
    wd = TH_DAY.get(day_name, -1)
    allow_days = set([0,1,2,3,4]) if group_kind == "ภาคปกติ" else set([0,1,2,3,4,5,6])
    if wd not in allow_days:
        return True
    start_ok, stop_ok = t(8,0), t(20,0)
    return not (s >= start_ok and e <= stop_ok)

def building(room: str) -> str:
    # แยกตึกจากชื่อเช่น "ทค1_201" -> "ทค1"
    return room.split("_")[0] if room and "_" in room else room or ""

def evaluate_individual(individual, group_kind_resolver=lambda g: "ภาคปกติ"):
    """
    individual: รายการ dict ของคาบเรียน แต่ละ g ควรมีคีย์อย่างน้อย:
      ['teacher','student_group','room','day_of_week','start_time','stop_time','hours','type','subject_code','subject_name']
    group_kind_resolver(g) -> 'ภาคปกติ' | 'ภาคพิเศษ' (ระบุจากกลุ่มเรียน/หลักสูตรของก้อนนั้น)
    """
    penalty = 0

    # ---- 0) เตรียมกลุ่มตาม day/teacher/group/room ----
    by_day = defaultdict(list)
    for g in individual:
        by_day[g["day_of_week"]].append(g)

    # ---- 1) Hard: เวลาเริ่ม-สิ้นสุดถูกต้อง & duration/slot ----
    for g in individual:
        s, e = g["start_time"], g["stop_time"]
        if s >= e:
            penalty += WEIGHTS["invalid_time"]

        dur = minutes_between(s, e)
        # ให้ชั่วโมงเป็นจำนวนเต็ม (1 หรือ 2 ฯลฯ) และตรงกับ hours*60
        if "hours" in g and isinstance(g["hours"], (int, float)):
            if dur != int(round(g["hours"] * 60)):
                penalty += WEIGHTS["duration_mismatch"]
        # จับให้ลง slot 60 นาที (จะเข้มขึ้นกว่าของเดิม)
        if dur % 60 != 0:
            penalty += WEIGHTS["slot_not_aligned"]

        # อยู่ในช่วง GroupAllow
        group_kind = group_kind_resolver(g)
        if is_outside_allow(g["day_of_week"], s, e, group_kind):
            penalty += WEIGHTS["out_of_group_allow"]

    # ---- 2) Hard: ซ้อนเวลาด้วย "ทับช่วง" จริง ----
    # สแกนเป็นคู่ภายในวันเดียวกัน
    for day, items in by_day.items():
        n = len(items)
        for i in range(n):
            for j in range(i+1, n):
                a, b = items[i], items[j]
                ov = overlap_minutes(a["start_time"], a["stop_time"], b["start_time"], b["stop_time"])
                if ov <= 0:
                    continue
                if a["teacher"] == b["teacher"]:
                    penalty += WEIGHTS["teacher_overlap"] + ov // 10  # โทษเพิ่มตามนาทีทับ
                if a["student_group"] == b["student_group"]:
                    penalty += WEIGHTS["group_overlap"] + ov // 10
                if a["room"] == b["room"]:
                    penalty += WEIGHTS["room_overlap"] + ov // 10

    # ---- 3) Soft: คุณภาพตารางเรียน ----
    LUNCH_S, LUNCH_E = t(12,0), t(13,0)

    # 3.1 ดึก/เช้าเกินไป & พักกลางวัน
    for g in individual:
        s, e = g["start_time"], g["stop_time"]
        if s < t(9,0):
            penalty += WEIGHTS["teach_too_early"]
        if e > t(18,0):
            penalty += WEIGHTS["teach_too_late"]
        if overlap_minutes(s, e, LUNCH_S, LUNCH_E) > 0:
            penalty += WEIGHTS["over_lunch"]

    # 3.2 กลุ่มเรียน: ภาระ/ช่องว่าง/จำนวนวิชาต่อวัน
    by_group_day = defaultdict(list)
    for g in individual:
        by_group_day[(g["student_group"], g["day_of_week"])].append(g)

    for (grp, day), items in by_group_day.items():
        # รวมชั่วโมง/วัน
        total_min = sum(minutes_between(x["start_time"], x["stop_time"]) for x in items)
        if total_min > 6*60:
            penalty += WEIGHTS["daily_overload"] * ((total_min - 6*60)//60 + 1)

        # จำนวนวิชา/วัน
        if len(items) > 3:
            penalty += WEIGHTS["many_subjects_a_day"] * (len(items)-3)

        # ช่องว่างเกิน 120 นาที
        items_sorted = sorted(items, key=lambda x: x["start_time"])
        for i in range(len(items_sorted)-1):
            gap = minutes_between(items_sorted[i]["stop_time"], items_sorted[i+1]["start_time"])
            if gap > 120:
                penalty += WEIGHTS["large_gaps"] * ((gap-120)//30 + 1)

        # เปลี่ยนตึกถ้าพักน้อย (< 60 นาที)
        for i in range(len(items_sorted)-1):
            a, b = items_sorted[i], items_sorted[i+1]
            gap = minutes_between(a["stop_time"], b["start_time"])
            if gap < 60 and building(a["room"]) != building(b["room"]):
                penalty += WEIGHTS["room_building_hops"]

    # 3.3 อาจารย์: ไม่ให้คาบอยู่ช่วงเดียวทั้งสัปดาห์ (เช้าล้วน/เย็นล้วน)
    by_teacher = defaultdict(list)
    for g in individual:
        by_teacher[g["teacher"]].append(g)
    def part_of_day(s: time):
        m = time_to_min(s)
        # เช้า: < 12:00, บ่าย: 12–16, เย็น: > 16
        return 0 if m < 12*60 else (1 if m <= 16*60 else 2)
    for tname, items in by_teacher.items():
        parts = {part_of_day(x["start_time"]) for x in items}
        if len(parts) == 1 and len(items) >= 3:
            # ถ้าสอน >=3 คาบ แต่กระจุกอยู่ช่วงเดียวทั้งหมด
            penalty += WEIGHTS["teacher_same_part_of_day"] * (len(items)-2)

    # fitness = ยิ่งโทษน้อย ยิ่งดี
    return -penalty

#======================================================================================================================
#======================================================================================================================
#======================================================================================================================




# def evaluate_individual(individual):
#     """คำนวณ fitness ของตาราง 1 ชุด (ยิ่ง conflict น้อย ยิ่งดี)"""
#     penalty = 0

#     # 1. เวลาเริ่ม–สิ้นสุดถูกต้อง
#     for g in individual:
#         if g["start_time"] >= g["stop_time"]:
#             penalty += 10

#     # 2. อาจารย์ห้ามซ้อน
#     seen = {}
#     for g in individual:
#         key = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
#         if key in seen:
#             penalty += 50
#         seen[key] = True

#     # 3. นักศึกษากลุ่มห้ามซ้อน
#     seen = {}
#     for g in individual:
#         key = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
#         if key in seen:
#             penalty += 50
#         seen[key] = True

#     # 4. ห้องห้ามซ้อน
#     seen = {}
#     for g in individual:
#         key = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])
#         if key in seen:
#             penalty += 50
#         seen[key] = True

#     # TODO: soft constraints เช่น balance, กระจายภาระ
#     return -penalty  # fitness = ยิ่งน้อยโทษ ยิ่งค่ามาก

def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame], generations: int = 100, pop_size: int = 50
):
    """เริ่ม Genetic Algorithm เพื่อสร้างตาราง"""
    courses = data["courses"]
    ga_free = data["ga_free"]

    # 1. สร้างประชากรเริ่มต้น
    population = initialize_population(courses, ga_free, pop_size)

    for gen in range(generations):
        # 2. ประเมิน fitness
        scored = [(evaluate_individual(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        # 3. เลือก top 50%
        survivors = [ind for _, ind in scored[: pop_size // 2]]

        # 4. Crossover/Mutation (ตรงนี้ยังเขียนแบบ dummy)
        children = []
        while len(children) + len(survivors) < pop_size:
            p1, p2 = random.sample(survivors, 2)
            child = random.choice([p1, p2])  # จริง ๆ ควร crossover กัน
            # Mutation: เปลี่ยน slot ของ gene แบบสุ่ม
            gene = random.choice(child)
            free_slot = ga_free.sample(1).to_dict(orient="records")[0]
            gene["day_of_week"] = free_slot["day_of_week"]
            gene["start_time"] = free_slot["start_time"]
            gene["stop_time"] = free_slot["stop_time"]
            gene["room"] = free_slot["room_name"]
            children.append(child)

        population = survivors + children

    # คืน individual ที่ดีที่สุด
    best_fitness, best_ind = max((evaluate_individual(ind), ind) for ind in population)
    return {"fitness": best_fitness, "schedule": best_ind}

# ==================== layer 3 end ==========================
def save_ga_result(schedule_rows):
    objs = []
    for row in schedule_rows:
        objs.append(GeneratedSchedule(
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
        ))
    GeneratedSchedule.objects.bulk_create(objs)

def run_genetic_algorithm_from_db() -> Dict[str, Any]:
    """ดึงข้อมูลทั้งหมด + เตรียมข้อมูลสำหรับ Genetic Algorithm (ยังไม่รันจริง)"""
    data = fetch_all_from_db()
    data["groupallows"] = apply_groupallow_blocking(
        data["groupallows"], data["weekactivities"]
    )

    ga_with_rooms = expand_groupallows_with_rooms(data["groupallows"], data["rooms"])
    ga_free = apply_preschedule_blocking(ga_with_rooms, data["preschedules"])

    data["ga_free"] = ga_free
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
