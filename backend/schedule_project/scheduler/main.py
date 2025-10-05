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

# main.py (ด้านบนสุด ใกล้ๆ import)
class GenerationCancelled(Exception):
    """โยนเมื่อมีการยกเลิกกลางคัน"""
    pass

def _check_cancel(cancel_event):
    if cancel_event and cancel_event.is_set():
        raise GenerationCancelled()


def _qs_to_df(qs, fields):
    """แปลง QuerySet ของ Django → DataFrame ของ pandas"""
    return pd.DataFrame(list(qs.values(*fields)))


def fetch_all_from_db(user) -> Dict[str, pd.DataFrame]:
    """ดึงข้อมูลดิบทั้งหมดจากฐานข้อมูลของ user (multi-user support)"""

    # ====== Courses ของ user ======
    courses = _qs_to_df(
        CourseSchedule.objects.filter(created_by=user),
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

    # ====== PreSchedules ของ user ======
    preschedules = _qs_to_df(
        PreSchedule.objects.filter(created_by=user),
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

    # ====== WeekActivities ของ user ======
    weekactivities = _qs_to_df(
        WeekActivity.objects.filter(created_by=user),
        [
            "id",
            "act_name_activity",
            "day_activity",
            "hours_activity",
            "start_time_activity",
            "stop_time_activity",
        ],
    )

    # ====== Rooms (global ใช้ร่วมกัน) ======
    rooms = _qs_to_df(
        Room.objects.select_related("room_type"),
        ["id", "name", "room_type__name"],
    ).rename(columns={"name": "room_name", "room_type__name": "room_type"})

    # ====== GroupAllows (global ใช้ร่วมกัน) ======
    groupallows = _qs_to_df(
        GroupAllow.objects.select_related("group_type", "slot"),
        [
            "id",
            "group_type__id",
            "group_type__name",
            "slot__day_of_week",
            "slot__start_time",
            "slot__stop_time",
        ],
    ).rename(
        columns={
            "group_type__id": "group_id",
            "group_type__name": "group_type",
            "slot__day_of_week": "day_of_week",
            "slot__start_time": "start_time",
            "slot__stop_time": "stop_time",
        }
    )

    # ===== เติม group_type_id ให้ courses (join กับ StudentGroup) =====
    sg_df = pd.DataFrame(list(StudentGroup.objects.values("name", "group_type_id")))

    if sg_df.empty:
        courses["group_type_id"] = pd.Series(dtype="Int64")
    else:
        sg_df["name_clean"] = sg_df["name"].fillna("").str.strip()

        courses["sg_name_clean"] = (
            courses["student_group_name_course"].fillna("").str.strip()
        )

        courses = courses.merge(
            sg_df[["name_clean", "group_type_id"]],
            left_on="sg_name_clean",
            right_on="name_clean",
            how="left",
        )

        courses["group_type_id"] = courses["group_type_id"].astype("Int64")

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
                "group_id",
                "group_type",
                "day_of_week",
                "start_time",
                "stop_time",
                "room_name",
            ]
        )

    # เตรียม columns ที่ต้องใช้
    ga = groupallows[
        ["group_id", "group_type", "day_of_week", "start_time", "stop_time"]
    ].copy()
    rm = rooms[["room_name", "room_type"]].copy()

    # cross join แบบง่าย: ใส่ key=1 แล้ว merge
    ga["__key"] = 1
    rm["__key"] = 1
    out = ga.merge(rm, on="__key").drop(columns="__key")

    # จัดลำดับคอลัมน์ให้อ่านง่าย
    return out[
        [
            "group_id",
            "group_type",
            "day_of_week",
            "start_time",
            "stop_time",
            "room_name",
            "room_type",
        ]
    ]


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
                "group_type_id",
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
            "group_type_id": r.get("group_type_id"),
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
    pop_size,
    seed=42,
    cancel_event=None,
):
    """
    สร้างประชากรเริ่มต้น:
    - ลูปตาม pop_size
    - ในแต่ละ individual: copy courses/ga_free
    - จัดเป็นก้อนวิชา (subject_code, section, group_type_id, type, room_type_course)
    - หา slot ที่ group_id == group_type_id และ room_type == room_type_course
    - ถ้าวางครบ → ติดตั้งเข้าตาราง / ลบออกจาก working set
    """
    count_runtime = 0
    rng = random.Random(seed)

    def has_conflict(current_rows, new_row):
        t_key = (
            new_row["teacher"],
            new_row["day_of_week"],
            new_row["start_time"],
            new_row["stop_time"],
        )
        s_key = (
            new_row["student_group"],
            new_row["day_of_week"],
            new_row["start_time"],
            new_row["stop_time"],
        )
        r_key = (
            new_row["room"],
            new_row["day_of_week"],
            new_row["start_time"],
            new_row["stop_time"],
        )
        return (
            (t_key in teacher_busy) or (s_key in student_busy) or (r_key in room_busy)
        )

    population = []
    group_cols = [
        "subject_code_course",
        "subject_name_course",
        "section_course",
        "teacher_name_course",
        "student_group_name_course",
        "room_type_course",
        "group_type_id",
        "type",
    ]

    def _norm(x):
        return str(x).strip().lower() if pd.notna(x) else ""

    for _ in range(pop_size):
        _check_cancel(cancel_event)
        work_courses = courses.copy().reset_index(drop=True)
        work_ga = ga_free.copy().reset_index(drop=True)
        individual = []

        teacher_busy, student_busy, room_busy = set(), set(), set()

        if work_courses.empty:
            population.append(individual)
            continue

        grouped = list(work_courses.groupby(group_cols, dropna=False))
        rng.shuffle(grouped)

        for gkey, df_units in grouped:
            _check_cancel(cancel_event)
            (
                sub_code,
                sub_name,
                section,
                teacher,
                student_group,
                room_type,
                gtype_id,
                ctype,
            ) = gkey
            hours_needed = len(df_units)

            if pd.isna(gtype_id):
                continue

            # --- filter ตาม group_id ---
            candidate = work_ga[work_ga["group_id"] == int(gtype_id)].copy()
            if candidate.empty:
                continue

            required_room_type = _norm(room_type)
            if "room_type" not in candidate.columns:
                continue
            candidate = candidate[
                candidate["room_type"].apply(_norm) == required_room_type
            ]
            if candidate.empty:
                continue

            candidate = candidate.sort_values(
                ["day_of_week", "start_time", "room_name"]
            ).reset_index(drop=True)

            placed_rows, used_idx = [], []

            for _, slot in candidate.iterrows():
                if len(placed_rows) >= hours_needed:
                    break
                _check_cancel(cancel_event)
                new_row = {
                    "subject_code": sub_code,
                    "subject_name": sub_name,
                    "teacher": teacher,
                    "student_group": student_group,
                    "section": section,
                    "type": ctype,
                    "hours": 1,
                    "day_of_week": slot["day_of_week"],
                    "start_time": slot["start_time"],
                    "stop_time": slot["stop_time"],
                    "room": slot["room_name"],
                    "group_type_id": gtype_id,
                    "room_type_course": room_type,
                    "unit_idx": int(df_units.iloc[0].get("unit_idx", 1)),
                    "unit_total": int(df_units.iloc[0].get("unit_total", hours_needed)),
                }
                if has_conflict(individual, new_row):
                    continue

                placed_rows.append(new_row)
                used_idx.append(slot.name)
                teacher_busy.add(
                    (
                        teacher,
                        new_row["day_of_week"],
                        new_row["start_time"],
                        new_row["stop_time"],
                    )
                )
                student_busy.add(
                    (
                        student_group,
                        new_row["day_of_week"],
                        new_row["start_time"],
                        new_row["stop_time"],
                    )
                )
                room_busy.add(
                    (
                        new_row["room"],
                        new_row["day_of_week"],
                        new_row["start_time"],
                        new_row["stop_time"],
                    )
                )

            if len(placed_rows) == hours_needed:
                individual.extend(placed_rows)
                if used_idx:
                    used_slots = candidate.loc[
                        used_idx,
                        ["day_of_week", "start_time", "stop_time", "room_name"],
                    ]
                    work_ga = work_ga.merge(
                        used_slots.assign(_used=1),
                        on=["day_of_week", "start_time", "stop_time", "room_name"],
                        how="left",
                    )
                    work_ga = (
                        work_ga[work_ga["_used"].isna()]
                        .drop(columns=["_used"])
                        .reset_index(drop=True)
                    )

                mask = pd.Series(True, index=work_courses.index)
                for col, val in zip(group_cols, gkey):
                    if pd.isna(val):
                        mask &= work_courses[col].isna()
                    else:
                        mask &= work_courses[col] == val
                work_courses = work_courses[~mask].reset_index(drop=True)
            else:
                print("❌ ไม่สามารถวางครบได้:", gkey)
                print("  hours_needed:", hours_needed, "แต่ได้จริง:", len(placed_rows))
                print("  placed_rows:")
                for r in placed_rows:
                    print("   ", r["subject_code"], r["subject_name"], 
                        r["teacher"], r["student_group"], 
                        r["day_of_week"], r["start_time"], "-", r["stop_time"], 
                        "room:", r["room"])
                print("-" * 50)

                # ไม่ discard busy เพื่อให้เห็นชัด ๆ ว่าก้อนไหนขาด
                continue

        population.append(individual)
        count_runtime = count_runtime + 1
        print(count_runtime)
    return population

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@


def make_allow_set(time_slot: pd.DataFrame):
    """
    สร้างชุด key ที่อนุญาตให้ใช้ (group_id, day, start, stop, room)
    ใช้ lookup เร็ว ๆ ใน fitness/mutation/repair
    """
    if time_slot is None or time_slot.empty:
        return set()
    return set(
        (
            int(r["group_id"]),
            r["day_of_week"],
            r["start_time"],
            r["stop_time"],
            r["room_name"],
        )
        for _, r in time_slot.iterrows()
    )


def is_conflict(existing_rows, g):
    """ชนไหม? (ครู/นักศึกษา/ห้อง ซ้อนเวลาเดียวกัน)"""
    t = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
    s = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
    r = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])

    for x in existing_rows:
        if (x["teacher"], x["day_of_week"], x["start_time"], x["stop_time"]) == t:
            return True
        if (x["student_group"], x["day_of_week"], x["start_time"], x["stop_time"]) == s:
            return True
        if (x["room"], x["day_of_week"], x["start_time"], x["stop_time"]) == r:
            return True
    return False


def find_slot_for_gene(
    gene, time_slot: pd.DataFrame, allow_set, rng: random.Random, max_tries=100, cancel_event=None,
):
    """
    หา slot ที่ถูกต้องสำหรับ gene:
      - group_allow: (group_type_id, day, start, stop, room) ต้องอยู่ใน allow_set
      - ไม่ชนกับสิ่งที่มีอยู่ (ผู้เรียกต้องเช็คเองตอน append)
    กลยุทธ์ง่าย ๆ: สุ่ม candidate จาก time_slot ตาม group_id แล้วลองทีละตัว
    """
    if pd.isna(gene.get("group_type_id", None)):
        return None  # ไม่มีสิทธิ์กลุ่ม ก็หาให้ไม่ได้

    cand = time_slot[time_slot["group_id"] == int(gene["group_type_id"])]
    if cand.empty:
        return None

    idxs = list(cand.index)
    rng.shuffle(idxs)

    tries = 0
    for i in idxs:
        tries += 1
        if tries > max_tries:
            break
        _check_cancel(cancel_event) 
        r = cand.loc[i]
        key = (
            int(gene["group_type_id"]),
            r["day_of_week"],
            r["start_time"],
            r["stop_time"],
            r["room_name"],
        )
        if key in allow_set:
            # คืน dict ของช่องใหม่ (ผู้เรียกจะใส่ต่อใน gene)
            return {
                "day_of_week": r["day_of_week"],
                "start_time": r["start_time"],
                "stop_time": r["stop_time"],
                "room": r["room_name"],
            }
    return None


# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@


def evaluate_individual(individual, allow_set, room_type_of=None):
    """
    คำนวณคะแนนแบบง่าย:
    +0 เริ่มจาก 0
    -50 ต่อ 1 เคสชน (ครู/นักศึกษา/ห้อง)
    -100 ต่อ 1 เคสที่ละเมิด group_allow (ไม่อยู่ใน allow_set)
    -10  ต่อ 1 เคส room_type ไม่ตรง (ถ้าส่ง room_type_of เข้ามา)
    +1   ต่อ 1 คาบที่ valid (เป็นรางวัลเล็ก ๆ)

    คืนค่าเป็น float (คะแนนรวม) — ยิ่งสูงยิ่งดี
    """
    penalty = 0
    reward = 0

    seen_t = set()
    seen_s = set()
    seen_r = set()
    for g in individual:
        # invalid time
        if g["start_time"] >= g["stop_time"]:
            penalty += 10

        t = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
        if t in seen_t:
            penalty += 50

        s = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
        if s in seen_s:
            penalty += 50

        r = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])
        if r in seen_r:
            penalty += 50

        seen_t.add(t)
        seen_s.add(s)
        seen_r.add(r)

        # group_allow check
        gtype = g.get("group_type_id", None)
        key = (
            int(gtype) if pd.notna(gtype) else None,
            g["day_of_week"],
            g["start_time"],
            g["stop_time"],
            g["room"],
        )
        if (gtype is None) or (key not in allow_set):
            penalty += 100

        if room_type_of is not None:
            req = g.get("room_type_course", None)
            actual = room_type_of.get(g["room"])
            if req and actual and str(req).strip() and str(actual).strip():
                if str(req).strip() != str(actual).strip():
                    penalty += 10

        # small reward for a valid placed hour
        reward += 1

        # print(f"Gen : best fitness = {reward - penalty}")
        # print()

    return reward - penalty


def course_key(g):
    return (
        g["subject_code"],
        g["section"],
        g["teacher"],
        g["student_group"],
        g["type"],
    )


def crossover(parent1, parent2, allow_set, time_slot, rng: random.Random, room_type_of, cancel_event=None):
    # ทำ bucket ของแต่ละพ่อแม่
    b1 = defaultdict(list)
    for g in parent1:
        b1[course_key(g)].append(g)
    b2 = defaultdict(list)
    for g in parent2:
        b2[course_key(g)].append(g)

    keys = set(b1.keys()) | set(b2.keys())
    child_raw = []
    for k in keys:
        pick_from_p1 = rng.random() < 0.5
        src = b1 if pick_from_p1 else b2
        if k in src:
            # copy ลึกเพื่อกัน side-effect
            child_raw.extend([dict(x) for x in src[k]])

    # repair: ไล่ทีละ gene ถ้าชนหรือผิด allow → หา slotใหม่
    child = []
    for g in child_raw:
        ok = True

        # group_allow check
        gtype = g.get("group_type_id", None)
        key = (
            int(gtype) if pd.notna(gtype) else None,
            g["day_of_week"],
            g["start_time"],
            g["stop_time"],
            g["room"],
        )
        if (
            (gtype is None)
            or (key not in allow_set)
            or is_conflict(child, g)
            or (
                g.get("room_type_course")
                and room_type_of.get(g["room"]) != g["room_type_course"]
            )
        ):
            slot = find_slot_for_gene(g, time_slot, allow_set, rng, cancel_event=cancel_event)
            if slot is None:
                ok = False
            else:
                g = {**g, **slot}
                if is_conflict(child, g):
                    ok = False

        if ok:
            child.append(g)

    return child


def mutate(
    individual, allow_set, time_slot, mut_rate: float, rng: random.Random, room_type_of, cancel_event=None,
):
    if not individual:
        return individual

    out = [dict(g) for g in individual]  # copy

    # MOVE
    for i, g in enumerate(out):
        if rng.random() < mut_rate:
            _check_cancel(cancel_event) 
            slot = find_slot_for_gene(g, time_slot, allow_set, rng, cancel_event=cancel_event)
            if slot:
                newg = {**g, **slot}
                if (
                    g.get("room_type_course")
                    and room_type_of.get(newg["room"]) != g["room_type_course"]
                ):
                    continue  # ข้าม mutation นี้ ถ้าห้องไม่ตรงประเภท

                if not is_conflict([x for j, x in enumerate(out) if j != i], newg):
                    out[i] = newg

    # SWAP (เบา ๆ)
    if len(out) >= 2 and rng.random() < mut_rate:
        i, j = rng.sample(range(len(out)), 2)
        gi, gj = dict(out[i]), dict(out[j])

        # ลองสลับช่องกัน
        gi_swapped = {
            **gi,
            "day_of_week": gj["day_of_week"],
            "start_time": gj["start_time"],
            "stop_time": gj["stop_time"],
            "room": gj["room"],
        }
        gj_swapped = {
            **gj,
            "day_of_week": gi["day_of_week"],
            "start_time": gi["start_time"],
            "stop_time": gi["stop_time"],
            "room": gi["room"],
        }

        # ตรวจ allow
        def allow_ok(g):
            gt = g.get("group_type_id", None)
            k = (
                int(gt) if pd.notna(gt) else None,
                g["day_of_week"],
                g["start_time"],
                g["stop_time"],
                g["room"],
            )
            return (gt is not None) and (k in allow_set)

        if allow_ok(gi_swapped) and allow_ok(gj_swapped):
            rest = [x for k, x in enumerate(out) if k not in (i, j)]
            if (not is_conflict(rest, gi_swapped)) and (
                not is_conflict(rest + [gi_swapped], gj_swapped)
            ):
                out[i] = gi_swapped
                out[j] = gj_swapped

    return out


def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame],
    generations,
    pop_size,
    elite_size: int = 3,
    cx_rate: float = 0.9,
    mut_rate: float = 0.2,
    seed: int = 42,
    cancel_event=None
):
    rng = random.Random(seed)

    courses = data["courses"]
    time_slot = data["time_slot"]

    # 1) ประชากรเริ่มต้น
    population = initialize_population(courses, time_slot, pop_size, seed=seed, cancel_event=cancel_event)
    print(len(population[0]))
    # 2) set สำหรับเช็ค allow และ mapping ชนิดห้อง (optional)
    allow_set = make_allow_set(time_slot)
    rooms_df = data.get("rooms", pd.DataFrame())
    room_type_of = {}
    if (
        not rooms_df.empty
        and "room_name" in rooms_df.columns
        and "room_type" in rooms_df.columns
    ):
        room_type_of = dict(zip(rooms_df["room_name"], rooms_df["room_type"]))

    def fitness(ind):
        return evaluate_individual(ind, allow_set, room_type_of)

    # ป้องกันกรณีไม่มีประชากร
    if not population:
        return {"fitness": float("-inf"), "schedule": []}

    # 3) วน GA
    for _ in range(generations):
        _check_cancel(cancel_event)

        scored = [(fitness(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        print(f"Gen {_}: best fitness = {scored[0][0]}")

        # เก็บตัวท็อปไว้ (elitism)
        new_pop = [scored[i][1] for i in range(min(elite_size, len(scored)))]

        # สร้างลูก
        parent_pool = [ind for _, ind in scored[: max(10, pop_size)]]
        while len(new_pop) < pop_size and parent_pool:
            _check_cancel(cancel_event)  # ← กันลูปยาวสร้างลูก

            p1, p2 = rng.sample(parent_pool, 2)
            if rng.random() < cx_rate:
                child = crossover(p1, p2, allow_set, time_slot, rng, room_type_of, cancel_event=cancel_event)
            else:
                child = [dict(g) for g in (p1 if rng.random() < 0.5 else p2)]
            child = mutate(child, allow_set, time_slot, mut_rate, rng, room_type_of, cancel_event=cancel_event)
            new_pop.append(child)

        population = new_pop

    # 4) คืนผลดีที่สุด
    best_fitness, best_ind = max(
        ((fitness(ind), ind) for ind in population), key=lambda x: x[0]
    )
    return {"fitness": best_fitness, "schedule": best_ind}


# ==================== layer 4 end ==========================
def save_ga_result(schedule_rows, user):
    """บันทึกผลลัพธ์ของ Genetic Algorithm ลงฐานข้อมูล โดยผูกกับ user"""
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
                created_by=user,   # ✅ ผูกกับ user
            )
        )
    GeneratedSchedule.objects.bulk_create(objs)


def run_genetic_algorithm_from_db(user, cancel_event=None) -> Dict[str, Any]:
    """ดึงข้อมูลเฉพาะของ user แล้วรัน Genetic Algorithm"""
    if user is None:
        raise ValueError("run_genetic_algorithm_from_db() ต้องการ user ที่ล็อกอินแล้ว")

    # ========= layer 1 ============
    data = fetch_all_from_db(user)  # ✅ ดึงเฉพาะข้อมูลของ user
    data["groupallows"] = apply_groupallow_blocking(
        data["groupallows"], data["weekactivities"]
    )

    # ========= layer 2 ============
    ga_with_rooms = expand_groupallows_with_rooms(data["groupallows"], data["rooms"])
    data["time_slot"] = apply_preschedule_blocking(
        ga_with_rooms, data["preschedules"]
    )

    # ========= layer 3 ============
    data["courses"] = explode_courses_to_units(data["courses"])

    # ========= layer 4 ============
    try:
        result = run_genetic_algorithm(
            data, generations=10, pop_size=10, cancel_event=cancel_event
        )
    except GenerationCancelled:
        raise  # ให้ views.py ดักและตอบ status 204

    # ✅ เคลียร์ตารางเก่าของ user ก่อน save ใหม่
    GeneratedSchedule.objects.filter(created_by=user).delete()

    # ✅ บันทึกผลใหม่
    save_ga_result(result["schedule"], user)

    best_sched = result["schedule"]
    return {
        "status": "success",
        "message": "Genetic Algorithm finished",
        "best_fitness": result["fitness"],
        "best_schedule": best_sched,
        "total_entries": len(best_sched),
    }
