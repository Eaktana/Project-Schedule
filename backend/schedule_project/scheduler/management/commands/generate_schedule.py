from django.core.management.base import BaseCommand
import pandas as pd
import random
from collections import defaultdict
import json
from datetime import datetime, time
from scheduler.models import TeacherSchedule, RoomSchedule, PreSchedule, ActivitySchedule, ScheduleInfo

class Command(BaseCommand):
    help = 'Generate schedule using genetic algorithm'

    def handle(self, *args, **options):
        # Global constants
        DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]
        HOURS = list(range(8, 20))  # 8 AM to 7 PM

        def get_blocked_times_from_activities(locked_activity_df):
            """Get blocked times from locked activities"""
            blocked_times = set()
            
            # ตรวจสอบ None และ empty DataFrame อย่างละเอียด
            if locked_activity_df is None:
                return blocked_times
            if hasattr(locked_activity_df, 'empty') and locked_activity_df.empty:
                return blocked_times
            if len(locked_activity_df) == 0:
                return blocked_times
                
            for _, row in locked_activity_df.iterrows():
                day = row.get("day")
                start_time = int(row.get("start_time", 0))
                stop_time = int(row.get("stop_time", 0))
                
                if day and day != "":  # ตรวจสอบว่า day ไม่เป็น None และไม่ว่าง
                    for hour in range(start_time, stop_time):
                        blocked_times.add(f"{day}_{hour}")
            
            return blocked_times

        def get_blocked_times_from_locked_courses(locked_df):
            blocked_times = set()
            
            # ตรวจสอบ None และ empty DataFrame อย่างละเอียด
            if locked_df is None:
                return blocked_times
            if hasattr(locked_df, 'empty') and locked_df.empty:
                return blocked_times
            if len(locked_df) == 0:
                return blocked_times
                
            for _, row in locked_df.iterrows():
                day = row.get("day")
                start_time = int(row.get("start_time", 0))
                stop_time = int(row.get("stop_time", 0))
                
                if day and day != "":  # ตรวจสอบว่า day ไม่เป็น None และไม่ว่าง
                    for hour in range(start_time, stop_time):
                        blocked_times.add(f"{day}_{hour}")
            
            return blocked_times

        def find_available_rooms(times, room_usage, valid_room_names):
            available_rooms = []
            # ตรวจสอบ None
            if not times or not valid_room_names:
                return available_rooms
                
            for room in valid_room_names:
                if not room:  # ข้าม room ที่เป็น None หรือว่าง
                    continue
                is_available = True
                for t in times:
                    if not t or "NO_VALID_TIME" in str(t):
                        continue
                    if room_usage and (room, t) in room_usage:
                        is_available = False
                        break
                if is_available:
                    available_rooms.append(room)
            return available_rooms

        def get_consecutive_times(hours_needed, blocked_times, room_usage, valid_room_names):
            max_attempts = 100
            
            # ตรวจสอบ None
            if blocked_times is None:
                blocked_times = set()
            if room_usage is None:
                room_usage = set()
            if valid_room_names is None:
                valid_room_names = []
                
            for _ in range(max_attempts):
                day = random.choice(DAYS)
                start_hour_options = [h for h in HOURS if h + hours_needed <= max(HOURS) + 1]
                if not start_hour_options:
                    continue
                start_hour = random.choice(start_hour_options)
                candidate_times = [f"{day}_{h}" for h in range(start_hour, start_hour + hours_needed)]
                
                # ตรวจสอบ blocked_times ก่อนใช้ in operator
                if blocked_times and any(t in blocked_times for t in candidate_times if t):
                    continue

                available_rooms = find_available_rooms(candidate_times, room_usage, valid_room_names)
                if available_rooms:
                    return {"times": candidate_times, "available_rooms": available_rooms}
            return {"times": [f"NO_VALID_TIME_{i}" for i in range(hours_needed)], "available_rooms": []}

        def get_valid_rooms(room_type, room_df):
            """Get valid rooms for a given room type from room_df"""
            if room_df is None or room_df.empty:
                return ["Room_001", "Room_002", "Room_003"]
            
            # ตรวจสอบ room_type
            if not room_type:
                room_type = ""
            
            if 'room_type' in room_df.columns:
                valid_rooms = room_df[room_df["room_type"] == room_type]["room_name"].tolist()
                if not valid_rooms:
                    valid_rooms = room_df["room_name"].tolist()
            else:
                valid_rooms = room_df["room_name"].tolist()
            
            # กรองห้องที่เป็น None หรือว่าง
            valid_rooms = [room for room in valid_rooms if room and str(room).strip()]
            
            # ถ้าไม่มีห้องเลย ให้ใช้ห้องเริ่มต้น
            if not valid_rooms:
                valid_rooms = ["Room_001", "Room_002", "Room_003"]
            
            return valid_rooms

        def extract_locked_schedule(locked_df):
            locked_list = []
            if locked_df is None:
                return locked_list
            if hasattr(locked_df, 'empty') and locked_df.empty:
                return locked_list
            if len(locked_df) == 0:
                return locked_list
        
            for _, row in locked_df.iterrows():
                day = row.get("day")
                if not day or day == "":  # ข้าม row ที่ไม่มี day
                    continue
            
                start_time = int(row.get("start_time", 0))
                stop_time = int(row.get("stop_time", 0))
                room_name = row.get("room_name", "")
                current_hour_for_slots = start_time
        
                if row.get("theory_slot", 0) > 0:
                    times_theory = [f"{day}_{h}" for h in range(current_hour_for_slots, current_hour_for_slots + row["theory_slot"])]
                    locked_list.append({
                        "course": str(row.get("subject_code", "")) + "_" + str(row.get("section", "")),
                        "subject_name": row.get("subject_name", ""),
                        "teacher": row.get("teacher_name", ""),
                        "type": "theory",
                        "room_type": row.get("room_type", ""),
                        "room": room_name,
                        "time": times_theory
                    })
                    current_hour_for_slots += row["theory_slot"]
        
                if row.get("lab_slot", 0) > 0:
                    times_lab = [f"{day}_{h}" for h in range(current_hour_for_slots, current_hour_for_slots + row["lab_slot"])]
                    locked_list.append({
                        "course": str(row.get("subject_code", "")) + "_" + str(row.get("section", "")) + "_lab",
                        "subject_name": row.get("subject_name", ""),
                        "teacher": row.get("teacher_name", ""),
                        "type": "lab",
                        "room_type": row.get("room_type", ""),
                        "room": room_name,
                        "time": times_lab
                    })
            return locked_list

        def extract_locked_activities(locked_activity_df):
            activity_list = []
            if locked_activity_df is None:
                return activity_list
            if hasattr(locked_activity_df, 'empty') and locked_activity_df.empty:
                return activity_list
            if len(locked_activity_df) == 0:
                return activity_list
        
            for _, row in locked_activity_df.iterrows():
                day = row.get("day")
                if not day or day == "":  # ข้าม row ที่ไม่มี day
                    continue
            
                start_time = int(row.get("start_time", 0))
                stop_time = int(row.get("stop_time", 0))
                times = [f"{day}_{h}" for h in range(start_time, stop_time)]
        
                activity_list.append({
                    "course": row.get("activity_name", ""),
                    "subject_name": row.get("activity_name", ""),
                    "teacher": None,
                    "type": "activity",
                    "room_type": None,
                    "room": None,
                    "time": times
                })
            return activity_list

        try:
            # 1. Fetch data from Django models
            teachers_data = list(TeacherSchedule.objects.values(
                'teacher_name_teacher', 'subject_code_teacher', 'subject_name_teacher',
                'room_type_teacher', 'section_teacher', 'theory_slot_amount_teacher',
                'lab_slot_amount_teacher'
            ))
            
            rooms_data = list(RoomSchedule.objects.values('room_name_room', 'room_type_room'))
            
            pre_schedules_data = list(PreSchedule.objects.values(
                'teacher_name_pre', 'subject_code_pre', 'subject_name_pre',
                'room_type_pre', 'section_pre', 'theory_slot_amount_pre',
                'lab_slot_amount_pre', 'day_pre', 'start_time_pre', 'stop_time_pre',
                'room_name_pre'
            ))
            
            activities_data = list(ActivitySchedule.objects.values(
                'act_name_activities', 'day_activities', 'start_time_activities', 'stop_time_activities'
            ))
            
            # ตรวจสอบข้อมูลก่อนสร้าง DataFrame
            if not teachers_data:
                result = {
                    "status": "error",
                    "message": "ไม่พบข้อมูลอาจารย์ในระบบ กรุณาเพิ่มข้อมูลอาจารย์ก่อน"
                }
                self.stdout.write(json.dumps(result, ensure_ascii=False))
                return
            
            # สร้าง DataFrame พร้อมตรวจสอบ None
            course_df = pd.DataFrame([{
                'teacher_name': t.get('teacher_name_teacher', '') or '',
                'subject_code': t.get('subject_code_teacher', '') or '',
                'subject_name': t.get('subject_name_teacher', '') or '',
                'room_type': t.get('room_type_teacher', '') or '',
                'section_count': int(t.get('section_teacher', 1)) if str(t.get('section_teacher', 1)).isdigit() else 1,
                'theory_slot': t.get('theory_slot_amount_teacher', 0) or 0,
                'lab_slot': t.get('lab_slot_amount_teacher', 0) or 0
            } for t in teachers_data]) if teachers_data else pd.DataFrame()

            room_df = pd.DataFrame([{
                'room_name': r.get('room_name_room', '') or '',
                'room_type': r.get('room_type_room', '') or ''
            } for r in rooms_data]) if rooms_data else pd.DataFrame()

            locked_df = pd.DataFrame([{
                'teacher_name': p.get('teacher_name_pre', '') or '',
                'subject_code': p.get('subject_code_pre', '') or '',
                'subject_name': p.get('subject_name_pre', '') or '',
                'room_type': p.get('room_type_pre', '') or '',
                'section': p.get('section_pre', '') or '',
                'theory_slot': p.get('theory_slot_amount_pre', 0) or 0,
                'lab_slot': p.get('lab_slot_amount_pre', 0) or 0,
                'day': p.get('day_pre', '') or '',
                'start_time': p['start_time_pre'].hour if isinstance(p.get('start_time_pre'), time) else 0,
                'stop_time': p['stop_time_pre'].hour if isinstance(p.get('stop_time_pre'), time) else 0,
                'room_name': p.get('room_name_pre', '') or ''
            } for p in pre_schedules_data]) if pre_schedules_data else pd.DataFrame()

            locked_activity_df = pd.DataFrame([{
                'activity_name': a.get('act_name_activities', '') or '',
                'day': a.get('day_activities', '') or '',
                'start_time': a['start_time_activities'].hour if isinstance(a.get('start_time_activities'), time) else 0,
                'stop_time': a['stop_time_activities'].hour if isinstance(a.get('stop_time_activities'), time) else 0
            } for a in activities_data]) if activities_data else pd.DataFrame()

            # 3. Generate courses list
            courses = []
            if not course_df.empty:
                for _, row in course_df.iterrows():
                    section_id = row["section_count"]
                    course_name_base = f"{row['subject_code']}_sec{section_id}"
                    
                    if row["theory_slot"] > 0:
                        courses.append({
                            "name": course_name_base,
                            "subject_name": row["subject_name"],
                            "teacher": row["teacher_name"],
                            "type": "theory",
                            "room_type": row["room_type"],
                            "hours": row["theory_slot"]
                        })
                    
                    if row["lab_slot"] > 0:
                        courses.append({
                            "name": course_name_base + "_lab",
                            "subject_name": row["subject_name"],
                            "teacher": row["teacher_name"],
                            "type": "lab",
                            "room_type": row["room_type"],
                            "hours": row["lab_slot"]
                        })

            locked_classes = extract_locked_schedule(locked_df)
            locked_activities = extract_locked_activities(locked_activity_df)
            all_locked_items = locked_classes + locked_activities
            locked_names = {c["course"] for c in locked_classes}

            all_blocked_times = get_blocked_times_from_activities(locked_activity_df).union(get_blocked_times_from_locked_courses(locked_df))

            def create_individual():
                individual = list(all_locked_items)
                used_times = set()
                room_usage = set()
                
                for item in individual:
                    if item and item.get("time"):
                        for t in item["time"]:
                            if t:
                                used_times.add(t)
                                if item.get("room"):
                                    room_usage.add((item["room"], t))
                
                blocked_times_for_individual = all_blocked_times.union(used_times) if all_blocked_times else used_times
                
                for c in courses:
                    if not c or c.get("name") in locked_names:
                        continue

                    valid_room_names = get_valid_rooms(c.get("room_type"), room_df)
                    result = get_consecutive_times(c.get("hours", 1), blocked_times_for_individual, room_usage, valid_room_names)
                    times = result["times"]
                    available_rooms = result["available_rooms"]
                    selected_room = random.choice(available_rooms) if available_rooms else "NO_VALID_ROOM"
                    
                    for t in times:
                        if t and "NO_VALID_TIME" not in str(t):
                            blocked_times_for_individual.add(t)
                            if selected_room != "NO_VALID_ROOM":
                                room_usage.add((selected_room, t))
                    
                    cls = {
                        "course": c.get("name", ""),
                        "subject_name": c.get("subject_name", c.get("name", "")),
                        "teacher": c.get("teacher", ""),
                        "type": c.get("type", ""),
                        "room_type": c.get("room_type", ""),
                        "room": selected_room,
                        "time": times
                    }
                    individual.append(cls)
                    
                return individual

            def fitness(individual):
                score = 0
                used = {"teacher_time": set(), "room_time": set()}
                room_balance_tracker = defaultdict(int)

                for cls in individual:
                    if not cls:
                        continue
                    if "NO_VALID_ROOM" in str(cls.get("room", "")):
                        score -= 100
                    if cls.get("time") and any("NO_VALID_TIME" in str(t) for t in cls["time"]):
                        score -= 100

                for cls in individual:
                    if not cls or not cls.get("time"):
                        continue
                    for t in cls["time"]:
                        if not t or "NO_VALID_TIME" in str(t):
                            continue
                            
                        if all_blocked_times and t in all_blocked_times:
                            score -= 50
                        
                        teacher = cls.get("teacher")
                        if teacher and (teacher, t) in used["teacher_time"]:
                            score -= 5
                        else:
                            if teacher:
                                used["teacher_time"].add((teacher, t))
                            score += 1

                        room = cls.get("room")
                        if room and (room, t) in used["room_time"]:
                            score -= 5
                        else:
                            if room and room != "NO_VALID_ROOM":
                                used["room_time"].add((room, t))
                                score += 1
                                room_balance_tracker[room] += 1

                    valid_times = [t for t in cls["time"] if t and "NO_VALID_TIME" not in str(t)]
                    if valid_times:
                        times_on_same_day = defaultdict(list)
                        for t in valid_times:
                            if "_" in str(t):
                                parts = str(t).split("_")
                                if len(parts) == 2 and parts[1].isdigit():
                                    day, hour = parts[0], int(parts[1])
                                    times_on_same_day[day].append(hour)
                        
                        for day, hours_list in times_on_same_day.items():
                            hours_list.sort()
                            if len(hours_list) > 1:
                                if all(hours_list[i+1] == hours_list[i] + 1 for i in range(len(hours_list)-1)):
                                    score += 10 * len(hours_list)
                                else:
                                    for i in range(len(hours_list) - 1):
                                        if hours_list[i+1] == hours_list[i] + 1:
                                            score += 2

                if room_balance_tracker:
                    usages = list(room_balance_tracker.values())
                    if usages:
                        max_usage = max(usages)
                        min_usage = min(usages)
                        room_balance_score = max_usage - min_usage
                        score -= room_balance_score * 2

                return score

            def crossover(p1, p2):
                locked_p1 = [cls.copy() for cls in p1 if cls and (cls.get("course") in locked_names or cls.get("type") == "activity")]
                unlocked_p1 = [cls.copy() for cls in p1 if cls and cls.get("course") not in locked_names and cls.get("type") != "activity"]
                unlocked_p2 = [cls.copy() for cls in p2 if cls and cls.get("course") not in locked_names and cls.get("type") != "activity"]

                if len(unlocked_p1) > 1:
                    point = random.randint(1, len(unlocked_p1)-1)
                    child_unlocked = unlocked_p1[:point] + unlocked_p2[point:]
                else:
                    child_unlocked = unlocked_p1

                return locked_p1 + child_unlocked

            def mutate(individual, rate=0.1):
                locked_items = [cls.copy() for cls in individual if cls and (cls.get("course") in locked_names or cls.get("type") == "activity")]
                unlocked_items = [cls.copy() for cls in individual if cls and cls.get("course") not in locked_names and cls.get("type") != "activity"]
                
                used_times = set()
                room_usage = set()
                
                for item in locked_items:
                    if item and item.get("time"):
                        for t in item["time"]:
                            if t:
                                used_times.add(t)
                                if item.get("room"):
                                    room_usage.add((item["room"], t))
                
                blocked_times_for_mutation = all_blocked_times.union(used_times) if all_blocked_times else used_times
                
                for cls in unlocked_items:
                    if not cls or random.random() >= rate:
                        continue
                        
                    valid_room_names = get_valid_rooms(cls.get("room_type"), room_df)
                    original_course_info = next((c for c in courses if c.get("name") == cls.get("course")), None)
                    if original_course_info:
                        hours_needed = original_course_info.get("hours", 1)
                    else:
                        hours_needed = len(cls.get("time", []))

                    result = get_consecutive_times(hours_needed, blocked_times_for_mutation, room_usage, valid_room_names)
                    
                    # ลบเวลาเก่าออกจาก blocked times
                    if cls.get("time"):
                        for t in cls["time"]:
                            if t and "NO_VALID_TIME" not in str(t):
                                blocked_times_for_mutation.discard(t)
                                if cls.get("room") != "NO_VALID_ROOM":
                                    room_usage.discard((cls["room"], t))

                    cls["time"] = result["times"]
                    available_rooms = result["available_rooms"]
                    cls["room"] = random.choice(available_rooms) if available_rooms else "NO_VALID_ROOM"
                    
                    # เพิ่มเวลาใหม่เข้าไปใน blocked times
                    for t in cls["time"]:
                        if t and "NO_VALID_TIME" not in str(t):
                            blocked_times_for_mutation.add(t)
                            if cls["room"] != "NO_VALID_ROOM":
                                room_usage.add((cls["room"], t))
                
                return locked_items + unlocked_items

            def genetic_algorithm(pop_size, generations):
                population = [create_individual() for _ in range(pop_size)]
                best_fitness_overall = float('-inf')
                best_individual_overall = None

                for gen in range(generations):
                    population.sort(key=fitness, reverse=True)
                    best = population[0]
                    best_fitness = fitness(best)

                    if best_fitness > best_fitness_overall:
                        best_fitness_overall = best_fitness
                        best_individual_overall = best.copy()
                    
                    if best_fitness >= 0 and "NO_VALID_TIME" not in str(best) and "NO_VALID_ROOM" not in str(best):
                        break

                    next_gen = population[:max(1, pop_size // 5)]
                    while len(next_gen) < pop_size:
                        p1, p2 = random.sample(population[:max(2, pop_size // 2)], 2)
                        child = crossover(p1, p2)
                        next_gen.append(mutate(child))
                    population = next_gen
                    
                return best_individual_overall if best_individual_overall else population[0]

            def save_schedule(schedule, output_path="schedule.csv"):
                schedule_data = []
                ScheduleInfo.objects.all().delete()
                
                for cls in schedule:
                    if not cls or not cls.get("time"):
                        continue
                    for t in cls["time"]:
                        if t and "NO_VALID_TIME" not in str(t) and "_" in str(t):
                            try:
                                day, hour = str(t).split("_")
                                schedule_entry = {
                                    "Course_Code": cls.get("course", ""),
                                    "Subject_Name": cls.get("subject_name", "N/A"),
                                    "Teacher": cls.get("teacher") if cls.get("teacher") else "N/A",
                                    "Room": cls.get("room") if cls.get("room") and cls.get("room") != "NO_VALID_ROOM" else "N/A",
                                    "Type": cls.get("type", ""),
                                    "Day": day,
                                    "Hour": int(hour),
                                    "Time_Slot": str(t)
                                }
                                schedule_data.append(schedule_entry)
                            except (ValueError, AttributeError):
                                continue
        
                schedule_data.sort(key=lambda x: (x["Day"], x["Hour"], x["Course_Code"]))
                schedule_df = pd.DataFrame(schedule_data)
                schedule_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                
                schedule_objects = []
                for entry in schedule_data:
                    schedule_objects.append(ScheduleInfo(
                        Course_Code=entry["Course_Code"],
                        Subject_Name=entry["Subject_Name"],
                        Teacher=entry["Teacher"],
                        Room=entry["Room"],
                        Type=entry["Type"],
                        Day=entry["Day"],
                        Hour=entry["Hour"],
                        Time_Slot=entry["Time_Slot"]
                    ))
                
                if schedule_objects:
                    ScheduleInfo.objects.bulk_create(schedule_objects)
                
                return schedule_df

            # Run the genetic algorithm
            best_schedule = genetic_algorithm(pop_size=30, generations=50)
            final_schedule = save_schedule(best_schedule, "schedule.csv")
            
            result = {
                "status": "success",
                "message": "ตารางสอนถูกสร้างสำเร็จและบันทึกลงฐานข้อมูลแล้ว",
                "file_path": "schedule.csv",
                "total_entries": len(final_schedule),
                "database_entries": len(final_schedule),
                "fitness_score": fitness(best_schedule)
            }
            
            self.stdout.write(json.dumps(result, ensure_ascii=False))
            
        except Exception as e:
            result = {
                "status": "error",
                "message": f"เกิดข้อผิดพลาด: {str(e)}"
            }
            self.stdout.write(json.dumps(result, ensure_ascii=False))
