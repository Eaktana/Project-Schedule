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

# ==================== utils ==========================

def _qs_to_df(qs, fields):
    """แปลง QuerySet ของ Django → DataFrame ของ pandas"""
    return pd.DataFrame(list(qs.values(*fields)))

def _t_to_min(t: time) -> int:
    return t.hour * 60 + t.minute

def _hour_keys(day: str, st: time, et: time, room: str):
    """
    แตก block เป็นคีย์รายชั่วโมง (15-17 → (15-16),(16-17)) เพื่อให้ตรวจชนแบบละเอียด
    key = (day, start, stop, room)
    """
    for h in range(st.hour, et.hour):
        yield (day, time(h, 0), time(h + 1, 0), room)

def _make_allowed_slot_set(ga_free_df: pd.DataFrame):
    """
    สร้าง allowed set จาก ga_free (ซึ่งเป็นผลลบ WeekActivity + Preschedule แล้ว)
    ใช้ตรวจว่าช่วงที่เลือก 'ถูกอนุญาต' จริงทุกชั่วโมง
    """
    if ga_free_df is None or ga_free_df.empty:
        return set()
    return {
        (r.day_of_week, r.start_time, r.stop_time, r.room_name)
        for r in ga_free_df.itertuples(index=False)
    }

# ==================== fetch ==========================

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

# ==================== layer 1 ==========================

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

# ==================== layer 2 ==========================

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

# ==================== GA core ==========================

def initialize_population(
    courses: pd.DataFrame, ga_free: pd.DataFrame, pop_size: int = 20
):
    """สร้างประชากรเริ่มต้น (initial population)"""
    population = []
    free_slots = ga_free.to_dict(orient="records")
    for _ in range(pop_size):
        individual = []
        for _, course in courses.iterrows():
            candidate = random.choice(free_slots)
            hours = course["theory_slot_amount_course"] or course["lab_slot_amount_course"]
            gene = {
                "subject_code": course["subject_code_course"],
                "subject_name": course["subject_name_course"],
                "teacher": course["teacher_name_course"],
                "student_group": course["student_group_name_course"],
                "section": course["section_course"],
                "type": "theory" if course["theory_slot_amount_course"] > 0 else "lab",
                "hours": hours,
                "day_of_week": candidate["day_of_week"],
                "start_time": candidate["start_time"],
                "stop_time": candidate["stop_time"],
                "room": candidate["room_name"],
            }
            individual.append(gene)
        population.append(individual)
    return population

def evaluate_individual_strict(individual, allowed_slots_set):
    """
    ให้คะแนนตารางแนว 'กันชน-เคารพช่วงเวลาอนุญาต-โบนัสช่วงต่อเนื่อง'
    - ชนห้อง/อาจารย์/กลุ่มเรียน: โทษหนัก
    - แทรกเวลานอก allowed: โทษหนัก
    - เวลาเริ่ม>=สิ้นสุด: โทษ
    - bonus ช่วงต่อเนื่องภายในวันเดียวกัน
    """
    score = 0
    used_teacher = set()
    used_room    = set()
    used_group   = set()

    for cls in individual:
        day  = cls["day_of_week"]
        st   = cls["start_time"]
        et   = cls["stop_time"]
        room = cls.get("room")
        tch  = cls.get("teacher")
        grp  = cls.get("student_group")

        # เวลาผิด
        if st >= et:
            score -= 100
            continue

        # 1) เช็คทุกชั่วโมงต้องอยู่ใน allowed
        outside = False
        for key in _hour_keys(day, st, et, room):
            if key not in allowed_slots_set:
                outside = True
                break
        if outside:
            score -= 1000  # โทษหนัก
        else:
            score += 20    # ได้วางในช่วงที่อนุญาต

        # 2) กันชน ครู/ห้อง/กลุ่ม (รายชั่วโมง)
        for key in _hour_keys(day, st, et, room):
            d, s, e, r = key
            if tch:
                tk = (tch, d, s, e)
                if tk in used_teacher:
                    score -= 1000
                else:
                    used_teacher.add(tk)
                    score += 30
            if r:
                rk = (r, d, s, e)
                if rk in used_room:
                    score -= 1000
                else:
                    used_room.add(rk)
                    score += 30
            if grp:
                gk = (grp, d, s, e)
                if gk in used_group:
                    score -= 1000
                else:
                    used_group.add(gk)
                    score += 30

    # 3) โบนัสช่วงต่อเนื่อง/คาบติดกันในวันเดียวกัน ต่อคลาส
    for cls in individual:
        times = []
        day  = cls["day_of_week"]
        st   = cls["start_time"]
        et   = cls["stop_time"]
        for h in range(st.hour, et.hour):
            times.append((day, h))
        if not times:
            continue
        times.sort()
        bonus = 0
        for i in range(1, len(times)):
            if times[i][0] == times[i-1][0] and times[i][1] == times[i-1][1] + 1:
                bonus += 5
        score += bonus

    return score

def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame], generations: int = 50, pop_size: int = 20
):
    """เริ่ม Genetic Algorithm เพื่อสร้างตาราง (strict evaluator)"""
    courses = data["courses"]
    ga_free = data["ga_free"]

    # allowed set สำหรับ evaluator (คำนวณครั้งเดียว)
    allowed_slots_set = _make_allowed_slot_set(ga_free)

    # 1) ประชากรเริ่มต้น
    population = initialize_population(courses, ga_free, pop_size)

    for gen in range(generations):
        # 2) ประเมิน
        scored = [(evaluate_individual_strict(ind, allowed_slots_set), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        # 3) เลือก top 50%
        survivors = [ind for _, ind in scored[: pop_size // 2]]

        # 4) Crossover/Mutation (ยังแบบง่าย)
        children = []
        while len(children) + len(survivors) < pop_size:
            p1, p2 = random.sample(survivors, 2)
            child = random.choice([p1, p2])  # TODO: ปรับเป็น crossover จริง
            # Mutation: เปลี่ยน slot ของ gene แบบสุ่ม 1 รายการ
            gene = random.choice(child)
            free_slot = ga_free.sample(1).to_dict(orient="records")[0]
            gene["day_of_week"] = free_slot["day_of_week"]
            gene["start_time"]  = free_slot["start_time"]
            gene["stop_time"]   = free_slot["stop_time"]
            gene["room"]        = free_slot["room_name"]
            children.append(child)

        population = survivors + children

    # คืน individual ที่ดีที่สุด
    best_fitness, best_ind = max((evaluate_individual_strict(ind, allowed_slots_set), ind) for ind in population)
    return {"fitness": best_fitness, "schedule": best_ind}

# ==================== persist ==========================

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

# ==================== pipeline ==========================

def run_genetic_algorithm_from_db() -> Dict[str, Any]:
    """ดึงข้อมูลทั้งหมด + เตรียมข้อมูล + รัน Genetic Algorithm + บันทึกผล"""
    data = fetch_all_from_db()

    # ลบช่วงที่ชน WeekActivity ออกจาก groupallows
    data["groupallows"] = apply_groupallow_blocking(
        data["groupallows"], data["weekactivities"]
    )

    # ขยาย groupallows ให้มีทุกห้อง แล้วลบช่วงที่ชน Preschedule ออกอีกชั้น
    ga_with_rooms = expand_groupallows_with_rooms(data["groupallows"], data["rooms"])
    ga_free = apply_preschedule_blocking(ga_with_rooms, data["preschedules"])

    data["ga_free"] = ga_free

    # รัน GA แบบ strict evaluator
    result = run_genetic_algorithm(data, generations=100, pop_size=50)
    save_ga_result(result["schedule"])

    return {
        "status": "success",
        "message": "Genetic Algorithm finished",
        "best_fitness": result["fitness"],
        "best_schedule": result["schedule"],  # ตารางที่ได้
    }
