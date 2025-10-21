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
import os

from tabulate import tabulate

# ================== Cancel & Utils ==================

class GenerationCancelled(Exception):
    """โยนเมื่อมีการยกเลิกกลางคัน"""
    pass

def _check_cancel(cancel_event):
    if cancel_event and cancel_event.is_set():
        raise GenerationCancelled()

def _qs_to_df(qs, fields):
    """แปลง QuerySet ของ Django → DataFrame ของ pandas"""
    return pd.DataFrame(list(qs.values(*fields)))

def _norm(x):
    return str(x).strip().lower() if pd.notna(x) else ""

# ================== Fetch layer-0 ===================

def fetch_all_from_db(user) -> Dict[str, pd.DataFrame]:
    """ดึงข้อมูลดิบทั้งหมดจากฐานข้อมูลของ user (multi-user support)"""
    if user is None:
        raise ValueError("fetch_all_from_db() ต้องการ user ที่ล็อกอินแล้ว")

    # Courses ของ user
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

    # PreSchedules ของ user
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

    # WeekActivities ของ user
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

    # Rooms (scoped by user)
    rooms = _qs_to_df(
        Room.objects.select_related("room_type")
            .filter(created_by=user, is_active=True),   # << กรองเฉพาะห้องที่ใช้งาน
        ["id", "name", "room_type__name"],
    ).rename(columns={"name": "room_name", "room_type__name": "room_type"})

    # GroupAllows (scoped by user)
    groupallows = _qs_to_df(
        GroupAllow.objects.select_related("group_type", "slot").filter(created_by=user),
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

    # เติม group_type_id ให้ courses (join กับ StudentGroup)
    sg_df = pd.DataFrame(
        list(StudentGroup.objects.filter(created_by=user).values("name", "group_type_id"))
    )
    if sg_df.empty:
        courses["group_type_id"] = pd.Series(dtype="Int64")
    else:
        sg_df["name_clean"] = sg_df["name"].fillna("").str.strip()
        courses["sg_name_clean"] = courses["student_group_name_course"].fillna("").str.strip()
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

# ==================== layer 1 ======================= 

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
        sh = int(getattr(st, "hour", 0)); eh = int(getattr(et, "hour", 0))
        if eh <= sh:
            continue
        for h in range(sh, eh):
            rows.append({"day_of_week": day_th, "start_time": time(h,0), "stop_time": time(h+1,0)})
    return pd.DataFrame(rows, columns=["day_of_week", "start_time", "stop_time"])

def apply_groupallow_blocking(groupallows: pd.DataFrame, weekactivities: pd.DataFrame) -> pd.DataFrame:
    """ลบช่วงเวลาของ groupallows ที่ทับกับกิจกรรมออก"""
    blocked = expand_weekactivities_to_slots(weekactivities)
    if groupallows.empty or blocked.empty:
        return groupallows
    merged = groupallows.merge(
        blocked, on=["day_of_week", "start_time", "stop_time"], how="left", indicator=True
    )
    return merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

# ==================== layer 2 =======================

def expand_groupallows_with_rooms(groupallows: pd.DataFrame, rooms: pd.DataFrame) -> pd.DataFrame:
    """ขยาย groupallows ให้มีทุกห้อง (เพิ่มคอลัมน์ room_name) ด้วย cross join"""
    if groupallows.empty or rooms.empty:
        return pd.DataFrame(
            columns=["group_id","group_type","day_of_week","start_time","stop_time","room_name","room_type"]
        )
    ga = groupallows[["group_id","group_type","day_of_week","start_time","stop_time"]].copy()
    rm = rooms[["room_name","room_type"]].copy()
    ga["__key"] = 1; rm["__key"] = 1
    out = ga.merge(rm, on="__key").drop(columns="__key")
    return out[["group_id","group_type","day_of_week","start_time","stop_time","room_name","room_type"]]

def expand_preschedules_to_slots(preschedules: pd.DataFrame) -> pd.DataFrame:
    """แตก Preschedule เป็นช่วงรายชั่วโมง + ชื่อห้อง (ไทยล้วน)"""
    if preschedules is None or preschedules.empty:
        return pd.DataFrame(columns=["day_of_week","start_time","stop_time","room_name"])
    rows = []
    for _, r in preschedules.iterrows():
        day_th = (r.get("day_pre") or "").strip()
        st = r.get("start_time_pre"); et = r.get("stop_time_pre")
        room = (r.get("room_name_pre") or "").strip()
        if pd.isna(st) or pd.isna(et) or not st or not et or not room:
            continue
        sh = int(getattr(st, "hour", 0)); eh = int(getattr(et, "hour", 0))
        if eh <= sh:
            continue
        for h in range(sh, eh):
            rows.append({
                "day_of_week": day_th, "start_time": time(h,0), "stop_time": time(h+1,0), "room_name": room
            })
    return pd.DataFrame(rows, columns=["day_of_week","start_time","stop_time","room_name"])

def apply_preschedule_blocking(ga_with_rooms: pd.DataFrame, preschedules: pd.DataFrame) -> pd.DataFrame:
    """ลบช่วงที่ถูกจองใน preschedules (วัน/เวลา/ห้อง) ออกจาก groupallows ที่ขยายแล้ว"""
    blocked = expand_preschedules_to_slots(preschedules)
    if ga_with_rooms.empty or blocked.empty:
        return ga_with_rooms
    merged = ga_with_rooms.merge(
        blocked, on=["day_of_week","start_time","stop_time","room_name"], how="left", indicator=True
    )
    return merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

# ==================== layer 3 =======================

def explode_courses_to_units(courses: pd.DataFrame) -> pd.DataFrame:
    """
    แตกแต่ละวิชาออกเป็นหน่วยชั่วโมง:
      - theory_slot_amount_course → type="theory", N แถว
      - lab_slot_amount_course    → type="lab",    M แถว
      หน่วยละ 1 ชั่วโมง
    """
    if courses is None or courses.empty:
        return pd.DataFrame(
            columns=[
                "id","teacher_name_course","subject_code_course","subject_name_course",
                "student_group_name_course","room_type_course","section_course","group_type_id",
                "type","hours","unit_idx","unit_total"
            ]
        )
    rows = []
    for _, r in courses.iterrows():
        theory_n = int(r.get("theory_slot_amount_course") or 0)
        lab_n    = int(r.get("lab_slot_amount_course") or 0)
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
        for i in range(theory_n):
            rows.append({**base,"type":"theory","hours":1,"unit_idx":i+1,"unit_total":theory_n})
        for i in range(lab_n):
            rows.append({**base,"type":"lab","hours":1,"unit_idx":i+1,"unit_total":lab_n})
    return pd.DataFrame(rows)

# ==================== Coverage / Capacity Tools ====================

# บังคับ “วางครบทุกหน่วย” (โทษหนักถ้ายังเหลือ)
REQUIRE_FULL_COVERAGE    = True
MISSING_UNIT_PENALTY     = 400
# ตรวจ capacity ล่วงหน้า (ตั้ง True เพื่อให้ raise หากไม่พอจริง)
HARD_FAIL_IF_IMPOSSIBLE  = False

def _preflight_capacity_check(data: Dict[str, pd.DataFrame]) -> list[dict]:
    """
    ตรวจว่า capacity (จำนวน time_slot ต่อ group_type_id) เพียงพอกับความต้องการหรือไม่
    return: รายการ deficit [{'group_id':..., 'required':..., 'capacity':..., 'deficit':...}, ...]
    """
    courses = data["courses"]
    time_slot = data["time_slot"]

    if courses.empty or time_slot.empty:
        return []

    # ต้องการต่อ group_type_id = จำนวนหน่วยทุกวิชาใน group นั้น
    req = courses.groupby("group_type_id", dropna=False).size().rename("required")
    # ความจุ = จำนวน slot ที่มีให้วาง (distinct by วัน/เวลา/ห้อง)
    cap = (
        time_slot
        .groupby("group_id")
        .apply(lambda df: df[["day_of_week","start_time","stop_time","room_name"]].drop_duplicates().shape[0])
        .rename("capacity")
    )
    merged = pd.concat([req, cap], axis=1).fillna(0)
    merged["required"] = merged["required"].astype(int)
    merged["capacity"] = merged["capacity"].astype(int)
    merged["deficit"] = (merged["required"] - merged["capacity"]).clip(lower=0).astype(int)

    deficits = []
    for gid, row in merged.iterrows():
        if pd.isna(gid):
            continue
        if row["deficit"] > 0:
            deficits.append({
                "group_id": int(gid),
                "required": int(row["required"]),
                "capacity": int(row["capacity"]),
                "deficit": int(row["deficit"]),
            })
    return deficits

def _greedy_fill_unassigned(
    individual: List[Dict[str, Any]],
    time_slot: pd.DataFrame,
    allow_set,
    room_type_of: Dict[str, str] | None,
    rng: random.Random,
    cancel_event=None,
):
    """
    เติมคาบที่ยัง unassigned แบบง่าย: ลองหา slot ถูกต้องที่ยังไม่ชนแล้ววางลงไป
    """
    if not individual:
        return individual

    out = [dict(g) for g in individual]

    # ทำชุด busy จากคาบที่วางแล้ว
    teacher_busy, student_busy, room_busy = set(), set(), set()
    for g in out:
        if _is_unassigned(g):
            continue
        t_key = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
        s_key = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
        r_key = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])
        teacher_busy.add(t_key); student_busy.add(s_key); room_busy.add(r_key)

    # เติมทีละตัว
    for i, g in enumerate(out):
        if not _is_unassigned(g):
            continue
        _check_cancel(cancel_event)
        slot = find_slot_for_gene(g, time_slot, allow_set, rng, max_tries=600, cancel_event=cancel_event)
        if not slot:
            continue
        newg = {**g, **slot, "assigned": True}

        # เช็ค room type ถ้าจำเป็น
        if room_type_of and g.get("room_type_course") and room_type_of.get(newg["room"]) != g["room_type_course"]:
            continue

        t_key = (newg["teacher"], newg["day_of_week"], newg["start_time"], newg["stop_time"])
        s_key = (newg["student_group"], newg["day_of_week"], newg["start_time"], newg["stop_time"])
        r_key = (newg["room"], newg["day_of_week"], newg["start_time"], newg["stop_time"])
        if t_key in teacher_busy or s_key in student_busy or r_key in room_busy:
            continue

        out[i] = newg
        teacher_busy.add(t_key); student_busy.add(s_key); room_busy.add(r_key)

    return out

# ==================== GA Helpers ====================

def make_allow_set(time_slot: pd.DataFrame):
    """สร้างชุด key สำหรับเช็ค allow เร็ว ๆ"""
    if time_slot is None or time_slot.empty:
        return set()
    return set(
        (int(r["group_id"]), r["day_of_week"], r["start_time"], r["stop_time"], r["room_name"])
        for _, r in time_slot.iterrows()
    )

def is_conflict(existing_rows, g):
    """ชนไหม? (ครู/นักศึกษา/ห้อง ซ้อนเวลาเดียวกัน)"""
    t = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
    s = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
    r = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])
    for x in existing_rows:
        if (x["teacher"], x["day_of_week"], x["start_time"], x["stop_time"]) == t: return True
        if (x["student_group"], x["day_of_week"], x["start_time"], x["stop_time"]) == s: return True
        if (x["room"], x["day_of_week"], x["start_time"], x["stop_time"]) == r: return True
    return False

def _is_unassigned(g: Dict[str, Any]) -> bool:
    """gene ที่ยังไม่วาง (ไม่มีวัน/เวลา/ห้อง หรือ flagged)"""
    return (not g.get("assigned")) or any(
        g.get(k) is None for k in ("day_of_week","start_time","stop_time","room")
    )

def _make_unassigned_gene(base_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subject_code": base_info["sub_code"],
        "subject_name": base_info["sub_name"],
        "teacher": base_info["teacher"],
        "student_group": base_info["student_group"],
        "section": base_info["section"],
        "type": base_info["ctype"],
        "hours": 1,
        "day_of_week": None,
        "start_time": None,
        "stop_time": None,
        "room": None,
        "group_type_id": base_info["gtype_id"],
        "room_type_course": base_info["room_type"],
        "unit_idx": base_info["unit_idx"],
        "unit_total": base_info["unit_total"],
        "assigned": False,
    }

def find_slot_for_gene(
    gene, time_slot: pd.DataFrame, allow_set, rng: random.Random, max_tries=300, cancel_event=None
):
    """
    หา slot ที่ถูกต้องสำหรับ gene:
      - group_allow: (group_type_id, day, start, stop, room) ต้องอยู่ใน allow_set
      - ไม่ชน (ผู้เรียกจะเช็คเองตอน append)
      - ไม่บังคับ room_type ที่นี่ (ปล่อยไปลงโทษใน fitness)
    """
    if pd.isna(gene.get("group_type_id", None)):
        return None
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
        key = (int(gene["group_type_id"]), r["day_of_week"], r["start_time"], r["stop_time"], r["room_name"])
        if key in allow_set:
            return {
                "day_of_week": r["day_of_week"],
                "start_time": r["start_time"],
                "stop_time": r["stop_time"],
                "room": r["room_name"],
                "assigned": True,
            }
    return None

# ===== Day/Time ordering helpers (for Theory→Lab order) =====
DAY_ORDER = {
    "จันทร์": 1, "อังคาร": 2, "พุธ": 3, "พฤหัสบดี": 4, "ศุกร์": 5, "เสาร์": 6, "อาทิตย์": 7,
    "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6, "Sun": 7,
}

def _slot_order_key(g: Dict[str, Any]) -> Tuple[int, time]:
    """แปลง (day, start_time) ให้เรียงได้; unassigned จะไปท้ายสุด"""
    d = g.get("day_of_week")
    st = g.get("start_time")
    if d is None or st is None:
        return (99, time(23, 59))
    return (DAY_ORDER.get(str(d).strip(), 99), st)

# ===== Contiguity scoring (same-day back-to-back) =====
# ใช้ “ต่อชนิด” (type) + “วันเดียวกัน” ภายในคีย์เดียวกัน (subject, section, teacher, group)
CONTIG_ADJACENT_BONUS = 50      # 70 ต่อ "คู่คาบที่ติดกัน"
CONTIG_GAP_PENALTY     = 30      # 70 ต่อ "ช่องว่าง" ระหว่างคาบในวันเดียวกัน
CONTIG_SEGMENT_PENALTY = 20       # 50 ต่อก้อน (segment) ที่เพิ่มในวันเดียวกัน

REQUIRE_SAME_ROOM_FOR_CONTIG = False  # True = ต้องอยู่ห้องเดียวกันถึงจะถือว่าติดกัน

def _contiguity_score(individual: List[Dict[str, Any]]) -> int:
    """
    ให้คะแนนความต่อเนื่องรายวิชา/ประเภท ใน 'วันเดียวกัน'
    group key = (subject_code, section, teacher, student_group, type, day_of_week)
    - คิดเฉพาะคาบที่ assigned ครบ (day/start/stop/room)
    - ติดกัน (back-to-back) ได้โบนัส
    - มีช่องว่าง (gap) ถูกหักคะแนน
    - หากหนึ่งวันถูกแยกเป็นหลายก้อน (segments) จะโดนหักเพิ่มตามจำนวนก้อน-1
    """
    assigned = [
        g for g in individual
        if not (
            (not g.get("assigned"))
            or g.get("day_of_week") is None
            or g.get("start_time") is None
            or g.get("stop_time") is None
            or g.get("room") is None
        )
    ]
    if not assigned:
        return 0

    by_key: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for g in assigned:
        key = (
            g["subject_code"],
            g["section"],
            g["teacher"],
            g["student_group"],
            str(g.get("type","")).strip().lower(),
            g["day_of_week"],
        )
        by_key[key].append(g)

    total = 0
    for key, genes in by_key.items():
        genes = sorted(genes, key=lambda x: x["start_time"])
        if len(genes) <= 1:
            continue

        segments = 1
        for i in range(len(genes)-1):
            cur, nxt = genes[i], genes[i+1]
            same_room_ok = (cur["room"] == nxt["room"]) if REQUIRE_SAME_ROOM_FOR_CONTIG else True
            if cur["stop_time"] == nxt["start_time"] and same_room_ok:
                total += CONTIG_ADJACENT_BONUS
            elif cur["stop_time"] < nxt["start_time"]:
                total -= CONTIG_GAP_PENALTY
                segments += 1
            else:
                # overlap ไม่ให้โบนัส/โทษเพิ่ม (มีบทลงโทษจากกฎ conflict อยู่แล้ว)
                pass

        if segments > 1:
            total -= CONTIG_SEGMENT_PENALTY * (segments - 1)

    return total

# ================= Initialize (diverse & partial) ==============

def initialize_population(
    courses: pd.DataFrame,
    ga_free: pd.DataFrame,
    pop_size,
    seed=42,
    cancel_event=None,
):
    """
    ประชากรเริ่มต้น (ยอม partial + unassigned):
      - จัดเป็นก้อนตาม subject+section+teacher+group+type+room_type+group_type
      - พยายามวางเท่าที่ทำได้ (หลีกเลี่ยงชน)
      - ชั่วโมงที่เหลือ สร้าง gene 'unassigned' ไว้ให้ GA ซ่อม
      - soft room_type filter: 70% ใช้ตรงประเภท, 30% ปล่อยหลวมเพื่อกระจาย
      - (ปรับเล็กน้อย) ดันกลุ่มที่ type="theory" มาก่อน เพื่อช่วยโอกาส Theory→Lab
    """
    base_rng = random.Random(seed)
    population = []

    group_cols = [
        "subject_code_course","subject_name_course","section_course",
        "teacher_name_course","student_group_name_course","room_type_course",
        "group_type_id","type",
    ]

    for _ in range(pop_size):
        rng = random.Random(base_rng.getrandbits(64))
        _check_cancel(cancel_event)
        work_courses = courses.copy().reset_index(drop=True)
        work_ga = ga_free.copy().reset_index(drop=True)
        individual = []

        teacher_busy, student_busy, room_busy = set(), set(), set()

        if work_courses.empty:
            population.append(individual); continue

        grouped = list(work_courses.groupby(group_cols, dropna=False))
        rng.shuffle(grouped)

        # ดัน theory ก่อน (ยังสุ่มลำดับกลุ่มอยู่ แต่ให้ priority เล็กน้อย)
        def _key_theory_first(item):
            gkey, _df = item
            _type = str(gkey[-1]).strip().lower()
            return 0 if _type == "theory" else 1
        grouped.sort(key=_key_theory_first)

        for gkey, df_units in grouped:
            _check_cancel(cancel_event)
            (sub_code, sub_name, section, teacher, student_group, room_type, gtype_id, ctype) = gkey
            hours_needed = len(df_units)
            if pd.isna(gtype_id):
                base_info = {
                    "sub_code": sub_code, "sub_name": sub_name, "section": section,
                    "teacher": teacher, "student_group": student_group, "room_type": room_type,
                    "gtype_id": gtype_id, "ctype": ctype,
                    "unit_idx": int(df_units.iloc[0].get("unit_idx", 1)),
                    "unit_total": int(df_units.iloc[0].get("unit_total", hours_needed)),
                }
                for _m in range(hours_needed):
                    individual.append(_make_unassigned_gene(base_info))
                continue

            candidate = work_ga[work_ga["group_id"] == int(gtype_id)].copy()
            if candidate.empty:
                base_info = {
                    "sub_code": sub_code, "sub_name": sub_name, "section": section,
                    "teacher": teacher, "student_group": student_group, "room_type": room_type,
                    "gtype_id": gtype_id, "ctype": ctype,
                    "unit_idx": int(df_units.iloc[0].get("unit_idx", 1)),
                    "unit_total": int(df_units.iloc[0].get("unit_total", hours_needed)),
                }
                for _m in range(hours_needed):
                    individual.append(_make_unassigned_gene(base_info))
                continue

            required_room_type = _norm(room_type)
            if "room_type" in candidate.columns:
                mask = candidate["room_type"].apply(_norm) == required_room_type
                keep_strict = candidate[mask]
                keep_loose  = candidate[~mask]
                if not keep_strict.empty and rng.random() < 0.7:
                    candidate = keep_strict
                else:
                    candidate = pd.concat([keep_strict, keep_loose], ignore_index=True)

            idxs = list(candidate.index)
            rng.shuffle(idxs)
            candidate = candidate.loc[idxs].reset_index(drop=True)

            placed_rows, used_idx = [], []
            base_info = {
                "sub_code": sub_code, "sub_name": sub_name, "section": section,
                "teacher": teacher, "student_group": student_group, "room_type": room_type,
                "gtype_id": gtype_id, "ctype": ctype,
                "unit_idx": int(df_units.iloc[0].get("unit_idx", 1)),
                "unit_total": int(df_units.iloc[0].get("unit_total", hours_needed)),
            }

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
                    "unit_idx": base_info["unit_idx"],
                    "unit_total": base_info["unit_total"],
                    "assigned": True,
                }
                t_key = (teacher, new_row["day_of_week"], new_row["start_time"], new_row["stop_time"])
                s_key = (student_group, new_row["day_of_week"], new_row["start_time"], new_row["stop_time"])
                r_key = (new_row["room"], new_row["day_of_week"], new_row["start_time"], new_row["stop_time"])
                if (t_key in teacher_busy) or (s_key in student_busy) or (r_key in room_busy):
                    continue

                placed_rows.append(new_row)
                used_idx.append(slot.name)
                teacher_busy.add(t_key); student_busy.add(s_key); room_busy.add(r_key)

            individual.extend(placed_rows)

            missing = hours_needed - len(placed_rows)
            for _m in range(missing):
                individual.append(_make_unassigned_gene(base_info))

            if used_idx:
                used_slots = candidate.loc[used_idx, ["day_of_week","start_time","stop_time","room_name"]]
                work_ga = work_ga.merge(
                    used_slots.assign(_used=1),
                    on=["day_of_week","start_time","stop_time","room_name"],
                    how="left",
                )
                work_ga = work_ga[work_ga["_used"].isna()].drop(columns=["_used"]).reset_index(drop=True)

        population.append(individual)

    return population

# ==================== Fitness =======================

def evaluate_individual(individual, allow_set, room_type_of=None):
    penalty = 0
    reward = 0

    seen_t, seen_s, seen_r = set(), set(), set()

    # -------- ส่วนที่ 1: โทษ/รางวัลพื้นฐานต่อ gene --------
    for g in individual:
        if _is_unassigned(g):
            penalty += 50
            continue

        if g["start_time"] >= g["stop_time"]:
            penalty += 100

        t = (g["teacher"], g["day_of_week"], g["start_time"], g["stop_time"])
        s = (g["student_group"], g["day_of_week"], g["start_time"], g["stop_time"])
        r = (g["room"], g["day_of_week"], g["start_time"], g["stop_time"])

        if t in seen_t: penalty += 120
        if s in seen_s: penalty += 120
        if r in seen_r: penalty += 120

        seen_t.add(t); seen_s.add(s); seen_r.add(r)

        gtype = g.get("group_type_id", None)
        key = (
            int(gtype) if pd.notna(gtype) else None,
            g["day_of_week"], g["start_time"], g["stop_time"], g["room"]
        )
        if (gtype is None) or (key not in allow_set):
            penalty += 120

        if room_type_of is not None:
            req = g.get("room_type_course", None)
            actual = room_type_of.get(g["room"])
            if req and actual and str(req).strip() and str(actual).strip():
                if str(req).strip() != str(actual).strip():
                    penalty += 110

        reward += 50

    # -------- ส่วนที่ 2: บังคับลำดับ Theory → Lab ต่อรายวิชา/เซกชัน --------
    by_course = defaultdict(list)
    for g in individual:
        if _is_unassigned(g):
            continue
        k = (g["subject_code"], g["section"], g["teacher"], g["student_group"])
        by_course[k].append(g)

    ORDER_LAB_BEFORE_THEORY = 90
    ORDER_LAB_WITHOUT_THEORY = 0

    for k, genes in by_course.items():
        theory_slots = [g for g in genes if str(g.get("type","")).strip().lower() == "theory"]
        lab_slots    = [g for g in genes if str(g.get("type","")).strip().lower() == "lab"]

        if not lab_slots:
            continue
        if not theory_slots:
            penalty += ORDER_LAB_WITHOUT_THEORY * len(lab_slots)
            continue

        first_theory_key = min((_slot_order_key(g) for g in theory_slots), default=(99, time(23,59)))
        for lab in lab_slots:
            if _slot_order_key(lab) < first_theory_key:
                penalty += ORDER_LAB_BEFORE_THEORY

    # -------- ส่วนที่ 3: ให้คะแนนความต่อเนื่อง (contiguity) --------
    contig = _contiguity_score(individual)

    # -------- ส่วนที่ 4: บังคับวางครบ (ถ้าเปิดใช้) --------
    if REQUIRE_FULL_COVERAGE:
        missing = sum(1 for g in individual if _is_unassigned(g))
        if missing > 0:
            penalty += MISSING_UNIT_PENALTY * missing

    return reward - penalty + contig

def course_key(g):
    return (g["subject_code"], g["section"], g["teacher"], g["student_group"], g["type"])

# ==================== Crossover & Mutation ====================

def crossover(parent1, parent2, allow_set, time_slot, rng: random.Random, room_type_of, cancel_event=None):
    """one-point by-course + repair (หา slot ใหม่ถ้าผิด/ชน)"""
    b1, b2 = defaultdict(list), defaultdict(list)
    for g in parent1: b1[course_key(g)].append(g)
    for g in parent2: b2[course_key(g)].append(g)

    keys = set(b1.keys()) | set(b2.keys())
    child_raw = []
    for k in keys:
        pick_from_p1 = rng.random() < 0.5
        src = b1 if pick_from_p1 else b2
        if k in src:
            child_raw.extend([dict(x) for x in src[k]])

    child = []
    for g in child_raw:
        if _is_unassigned(g):
            child.append(g); continue

        gtype = g.get("group_type_id", None)
        key = (
            int(gtype) if pd.notna(gtype) else None,
            g["day_of_week"], g["start_time"], g["stop_time"], g["room"]
        )
        if (
            (gtype is None)
            or (key not in allow_set)
            or is_conflict(child, g)
            or (g.get("room_type_course") and room_type_of.get(g["room"]) != g["room_type_course"])
        ):
            slot = find_slot_for_gene(g, time_slot, allow_set, rng, cancel_event=cancel_event)
            if slot is None:
                g = {**g, "day_of_week": None, "start_time": None, "stop_time": None, "room": None, "assigned": False}
            else:
                g = {**g, **slot}
                if is_conflict(child, g):
                    g = {**g, "day_of_week": None, "start_time": None, "stop_time": None, "room": None, "assigned": False}
        child.append(g)

    return child

def mutate(individual, allow_set, time_slot, mut_rate: float, rng: random.Random, room_type_of, cancel_event=None):
    """สามเฟส: FILL (เติม unassigned) → MOVE → SWAP"""
    if not individual:
        return individual

    out = [dict(g) for g in individual]

    # (A) FILL
    for i, g in enumerate(out):
        if _is_unassigned(g):
            if rng.random() < max(mut_rate, 0.5):
                _check_cancel(cancel_event)
                slot = find_slot_for_gene(g, time_slot, allow_set, rng, cancel_event=cancel_event)
                if slot:
                    newg = {**g, **slot, "assigned": True}
                    if g.get("room_type_course") and room_type_of.get(newg["room"]) != g["room_type_course"]:
                        continue
                    if not is_conflict([x for j,x in enumerate(out) if j!=i], newg):
                        out[i] = newg

    # (B) MOVE
    for i, g in enumerate(out):
        if (not _is_unassigned(g)) and rng.random() < mut_rate:
            _check_cancel(cancel_event)
            slot = find_slot_for_gene(g, time_slot, allow_set, rng, cancel_event=cancel_event)
            if slot:
                newg = {**g, **slot}
                if g.get("room_type_course") and room_type_of.get(newg["room"]) != g["room_type_course"]:
                    continue
                if not is_conflict([x for j,x in enumerate(out) if j!=i], newg):
                    out[i] = newg

    # (C) SWAP
    if len(out) >= 2 and rng.random() < mut_rate:
        i, j = rng.sample(range(len(out)), 2)
        gi, gj = dict(out[i]), dict(out[j])

        if (not _is_unassigned(gi)) and (not _is_unassigned(gj)):
            gi_swapped = {**gi, "day_of_week": gj["day_of_week"], "start_time": gj["start_time"], "stop_time": gj["stop_time"], "room": gj["room"]}
            gj_swapped = {**gj, "day_of_week": gi["day_of_week"], "start_time": gi["start_time"], "stop_time": gi["stop_time"], "room": gi["room"]}

            def allow_ok(g):
                gt = g.get("group_type_id", None)
                k = (int(gt) if pd.notna(gt) else None, g["day_of_week"], g["start_time"], g["stop_time"], g["room"])
                return (gt is not None) and (k in allow_set)

            if allow_ok(gi_swapped) and allow_ok(gj_swapped):
                rest = [x for k, x in enumerate(out) if k not in (i, j)]
                if (not is_conflict(rest, gi_swapped)) and (not is_conflict(rest + [gi_swapped], gj_swapped)):
                    out[i] = gi_swapped
                    out[j] = gj_swapped

    return out

# ==================== GA Main =======================

def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame],
    generations,
    pop_size,
    elite_size,
    cx_rate,
    mut_rate,
    seed: int | None = None,   # << seed เป็น optional
    cancel_event=None
):
    if seed is None:
        seed = int.from_bytes(os.urandom(8), "big")  # << สุ่มใหม่ทุกรอบ
    rng = random.Random(seed)
    print(f"[GA] seed = {seed}")

    courses = data["courses"]
    time_slot = data["time_slot"]

    # 1) ประชากรเริ่มต้น
    population = initialize_population(courses, time_slot, pop_size, seed=seed, cancel_event=cancel_event)

    # 2) allow_set + room mapping
    allow_set = make_allow_set(time_slot)
    rooms_df = data.get("rooms", pd.DataFrame())
    room_type_of = {}
    if (not rooms_df.empty) and ("room_name" in rooms_df.columns) and ("room_type" in rooms_df.columns):
        room_type_of = dict(zip(rooms_df["room_name"], rooms_df["room_type"]))

    def fitness(ind):
        # สามารถเปิด debug เพิ่มเติมได้ถ้าต้องการ
        return evaluate_individual(ind, allow_set, room_type_of)

    if not population:
        return {"fitness": float("-inf"), "schedule": []}

    best_overall = None
    stagnant = 0
    last_best = None

    for gen in range(generations):
        _check_cancel(cancel_event)

        scored = [(fitness(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        print(f"\n=== Generation {gen} ===")
        print(f"Gen {gen}: best fitness = {scored[0][0]}")

        if (best_overall is None) or (scored[0][0] > best_overall[0]):
            best_overall = (scored[0][0], [dict(g) for g in scored[0][1]])

        if last_best is None or scored[0][0] > last_best:
            last_best = scored[0][0]; stagnant = 0
        else:
            stagnant += 1

        cur_mut = mut_rate * (1.3 if stagnant >= 3 else 1.0)

        new_pop = [scored[i][1] for i in range(min(elite_size, len(scored)))]

        top_k = max(2, int(0.4 * pop_size))
        parent_pool = [ind for _, ind in scored[:top_k]]
        rest = [ind for _, ind in scored[top_k:]]
        rng.shuffle(rest)
        parent_pool += rest[:max(2, int(0.1 * pop_size))]
        if not parent_pool:
            parent_pool = [ind for _, ind in scored]

        while len(new_pop) < pop_size:
            _check_cancel(cancel_event)
            p1, p2 = rng.sample(parent_pool, 2)
            if rng.random() < cx_rate:
                child = crossover(p1, p2, allow_set, time_slot, rng, room_type_of, cancel_event=cancel_event)
            else:
                child = [dict(g) for g in (p1 if rng.random() < 0.5 else p2)]
            child = mutate(child, allow_set, time_slot, cur_mut, rng, room_type_of, cancel_event=cancel_event)
            new_pop.append(child)

        population = new_pop

    final_best = max([(fitness(ind), ind) for ind in population], key=lambda x: x[0])
    if best_overall is None or final_best[0] >= best_overall[0]:
        best_fitness, best_ind = final_best
    else:
        best_fitness, best_ind = best_overall

    # Greedy fill รอบสุดท้าย เพื่ออุดหน่วยที่ยังขาด
    best_after_fill = _greedy_fill_unassigned(best_ind, time_slot, allow_set, room_type_of, rng, cancel_event=cancel_event)
    filled_fit = evaluate_individual(best_after_fill, allow_set, room_type_of)
    if filled_fit > best_fitness:
        best_fitness, best_ind = filled_fit, best_after_fill

    return {"fitness": best_fitness, "schedule": best_ind}

# ==================== Persist =======================

def save_ga_result(schedule_rows, user):
    """บันทึกผลลัพธ์ของ Genetic Algorithm ลงฐานข้อมูล โดยผูกกับ user"""
    objs = []
    for row in schedule_rows:
        if _is_unassigned(row):
            continue
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
                created_by=user,
            )
        )
    if objs:
        GeneratedSchedule.objects.bulk_create(objs)

# ==================== Orchestrator =======================

def run_genetic_algorithm_from_db(user, cancel_event=None) -> Dict[str, Any]:
    """ดึงข้อมูลเฉพาะของ user แล้วรัน Genetic Algorithm แบบค่อย ๆ พัฒนาไปหาผลลัพธ์ที่ดีที่สุด"""
    if user is None:
        raise ValueError("run_genetic_algorithm_from_db() ต้องการ user ที่ล็อกอินแล้ว")

    # ========= layer 1 ============
    data = fetch_all_from_db(user)
    data["groupallows"] = apply_groupallow_blocking(data["groupallows"], data["weekactivities"])

    # ========= layer 2 ============
    ga_with_rooms = expand_groupallows_with_rooms(data["groupallows"], data["rooms"])
    data["time_slot"] = apply_preschedule_blocking(ga_with_rooms, data["preschedules"])

    # ========= layer 3 ============
    data["courses"] = explode_courses_to_units(data["courses"])

    print("GA/groupallows days:", sorted(data["groupallows"]["day_of_week"].dropna().unique().tolist()) if not data["groupallows"].empty else [])
    print("GA/time_slot days:", sorted(data["time_slot"]["day_of_week"].dropna().unique().tolist()) if not data["time_slot"].empty else [])
    if not data["time_slot"].empty:
        print("time_slot by day:\n", data["time_slot"]["day_of_week"].value_counts())

    # ========= preflight capacity ============
    deficits = _preflight_capacity_check(data)
    if deficits:
        msg_lines = ["[WARN] slot ไม่พอต่อความต้องการ (group_type_id):"]
        for d in deficits:
            msg_lines.append(f" - group_id={d['group_id']}: required={d['required']}, capacity={d['capacity']}, deficit={d['deficit']}")
        print("\n".join(msg_lines))
        if HARD_FAIL_IF_IMPOSSIBLE:
            raise ValueError("\n".join(msg_lines))

    # ========= layer 4 ============
    try:
        result = run_genetic_algorithm(
            data,
            generations=200,  
            pop_size=50,         
            elite_size=2,
            cx_rate=0.1,
            mut_rate=0.1,
            seed=None,              
            cancel_event=cancel_event,
        )
    except GenerationCancelled:
        raise  # ให้ views.py ดักและตอบ status 204

    GeneratedSchedule.objects.filter(created_by=user).delete()
    save_ga_result(result["schedule"], user)

    best_sched = result["schedule"]
    return {
        "status": "success",
        "message": "Genetic Algorithm finished",
        "best_fitness": result["fitness"],
        "best_schedule": best_sched,
        "total_entries": len([r for r in best_sched if not _is_unassigned(r)]),
        "unassigned": sum(1 for r in best_sched if _is_unassigned(r)),
    }
