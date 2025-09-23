from django.urls import path
from . import views

urlpatterns = [
    # หน้าเว็บหลัก
    path('', views.home, name='home'),
    path('pre/', views.pre_page, name='pre'),
    path('course/', views.course_page, name='course'),
    path('weekactivity/', views.activity_page, name='weekactivity'),
    path('add/', views.add_info, name='add'),

    # APIs ที่มีอยู่แล้ว...
    path('api/test-program/', views.test_program_api, name='test_program_api'),
    path('api/schedule/generate/', views.generate_schedule_api, name='generate_schedule_api'),
    path('api/schedule/view/', views.view_schedule_api, name='view_schedule_api'),
    path('api/schedule/clear/', views.clear_schedule_api, name='clear_schedule_api'),
    path('api/schedule/download/', views.download_schedule, name='download_schedule'),
    path('api/schedule/delete-selected/', views.delete_selected_schedules_api, name='delete_selected_schedules_api'),
    path('api/schedule/view-generated/', views.view_generated_schedule_api, name='view_generated_schedule'),
    path("api/schedule/list/", views.list_generated_entities_api, name="schedule_list"),
    
     # Pre-Schedule APIs
    path('api/pre/', views.get_pre, name='get_pre'),
    path('api/pre/add/', views.add_pre, name='add_pre'),
    path('api/pre/update/<int:id>/', views.update_pre, name='update_pre'),
    path('api/pre/delete/<int:id>/', views.delete_pre, name='delete_pre'),
    path('upload/pre-csv/', views.upload_pre_csv, name='upload_pre_csv'),
    path("api/pre/delete-all/", views.pre_delete_all, name="pre_delete_all"),

    # Course APIs
    path('api/course/', views.get_courses, name='get_course'),
    path('api/course/add/', views.add_course, name='add_course'),
    path('api/course/bulk/', views.add_course_bulk, name='add_course_bulk'),
    path('api/course/update/<int:id>/', views.update_course, name='update_course'),
    path('api/course/delete/<int:id>/', views.delete_course, name='delete_course'),
    path('upload/course-csv/', views.upload_course_csv, name='upload_course_csv'),
    path('api/course/delete-all/', views.course_delete_all, name='course_delete_all'),
    
    # Lookups for course.js
    path('api/teachers/', views.teachers_lookup, name='teachers_lookup'),
    path('api/lookups/room-types/', views.room_types_lookup, name='room_types_lookup'),
    path('api/lookups/student-groups/', views.student_groups_lookup, name='student_groups_lookup'),

    # Weekactivity APIs
    path('api/activity/', views.get_activity, name='get_activity'),
    path('api/activity/add/', views.add_activity, name='add_activity'),
    path('api/activity/bulk/', views.add_activity_bulk, name='add_activity_bulk'),
    path('api/activity/update/<int:id>/', views.update_activity, name='update_activity'),
    path('api/activity/delete/<int:id>/', views.delete_activity, name='delete_activity'),
    path('upload/activity-csv/', views.upload_activity_csv, name='upload_activity_csv'),
    path('api/meta/days/', views.meta_days, name='meta_days'),
    path('api/meta/start-times/', views.meta_start_times, name='meta_start_times'),
    path('api/meta/stop-times/', views.meta_stop_times, name='meta_stop_times'),
    path('api/activity/delete-all/', views.activity_delete_all, name='activity_delete_all'),


    #AddPIS
    path('subject/', views.subject, name='subject'),
    path('teacher/', views.teacher, name='teacher'),
    path('studentgroup/', views.studentgroup, name='studentgroup'),
    path('grouptype/', views.grouptype, name='grouptype'),
    path('groupallow/', views.groupallow, name='groupallow'),
    path('room/', views.room, name='room'),
    path('roomtype/', views.roomtype, name='roomtype'),
    path('timeslot/', views.timeslot, name='timeslot'),
    
    # GroupAllow APIs
    path('api/groupallow/list/', views.groupallow_list, name='groupallow_list'),
    path('api/groupallow/add/', views.groupallow_add, name='groupallow_add'),
    path('api/groupallow/delete/<int:pk>/', views.groupallow_delete, name='groupallow_delete'),
    path('api/groupallow/delete-all/', views.groupallow_delete_all, name='groupallow_delete_all'),  # 👈 เพิ่ม

    
    # --- GroupType APIs ---
    path('api/grouptype/list/', views.grouptype_list, name='grouptype_list'),
    path('api/grouptype/add/', views.grouptype_add, name='grouptype_add'),
    path('api/grouptype/delete/<int:pk>/', views.grouptype_delete, name='grouptype_delete'),
    path('api/grouptype/delete-all/', views.grouptype_delete_all, name='grouptype_delete_all'),
    
    # --- Room APIs ---
    path('api/room/list/',   views.room_list,   name='room_list'),
    path('api/room/add/',    views.room_add,    name='room_add'),
    path('api/room/delete/<int:pk>/', views.room_delete, name='room_delete'),
    path("api/room/delete-all/", views.room_delete_all, name="room_delete_all"),

    # --- RoomType APIs ---
    path('api/roomtype/list/',   views.roomtype_list,   name='roomtype_list'),
    path('api/roomtype/add/',    views.roomtype_add,    name='roomtype_add'),
    path('api/roomtype/delete/<int:pk>/', views.roomtype_delete, name='roomtype_delete'),
    path('api/roomtype/delete-all/', views.roomtype_delete_all, name='roomtype_delete_all'),  # ✅

    
    # --- StudentGroup APIs ---
    path('api/studentgroup/list/',   views.studentgroup_list,   name='studentgroup_list'),
    path('api/studentgroup/add/',    views.studentgroup_add,    name='studentgroup_add'),
    path('api/studentgroup/delete/<int:pk>/', views.studentgroup_delete, name='studentgroup_delete'),
    path('api/studentgroup/delete-all/', views.studentgroup_delete_all, name='studentgroup_delete_all'),

    # Subject (RESTful)
    path('api/subjects/', views.subjects_collection, name='subjects_collection'),
    path('api/subjects/<int:pk>/', views.subjects_detail, name='subjects_detail'),
    path("api/subjects/", views.subject_delete_all, name="subject_delete_all"),
    
    # --- Teacher APIs ---
    path("api/teacher/list/", views.teacher_list, name="teacher_list"),
    path("api/teacher/add/", views.teacher_add, name="teacher_add"),
    path("api/teacher/update/<int:pk>/", views.teacher_update, name="teacher_update"),
    path("api/teacher/delete-all/", views.teacher_delete_all, name="teacher_delete_all"),
    path("api/teacher/delete/<int:pk>/", views.teacher_delete, name="teacher_delete"),
    
    # --- TimeSlot APIs ---
    path('api/timeslot/list/',   views.timeslot_list,   name='timeslot_list'),
    path('api/timeslot/add/',    views.timeslot_add,    name='timeslot_add'),
    path('api/timeslot/delete/<int:pk>/', views.timeslot_delete, name='timeslot_delete'),
    path('api/timeslot/delete-all/', views.timeslot_delete_all, name='timeslot_delete_all'),
]