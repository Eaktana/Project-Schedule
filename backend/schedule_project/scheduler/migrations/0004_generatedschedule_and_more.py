from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('scheduler', '0003_delete_activityschedule_alter_weekactivity_options_and_more'),
    ]

    operations = [
        # --- GeneratedSchedule: อัปเดต state อย่างเดียว (ตารางมีแล้ว) ---
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='GeneratedSchedule',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('subject_code', models.CharField(max_length=20)),
                        ('subject_name', models.CharField(max_length=100)),
                        ('teacher', models.CharField(blank=True, max_length=100, null=True)),
                        ('student_group', models.CharField(blank=True, max_length=100, null=True)),
                        ('section', models.CharField(blank=True, max_length=10, null=True)),
                        ('type', models.CharField(blank=True, max_length=20, null=True)),
                        ('hours', models.IntegerField(default=0)),
                        ('day_of_week', models.CharField(max_length=20)),
                        ('start_time', models.TimeField()),
                        ('stop_time', models.TimeField()),
                        ('room', models.CharField(blank=True, max_length=50, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                    ],
                ),
            ],
            database_operations=[],
        ),

        # --- RenameField: ปรับ state ว่าชื่อใหม่แล้ว (DB เปลี่ยนแล้ว) ---
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(
                    model_name='courseschedule',
                    old_name='curriculum_type_course',
                    new_name='student_group_name_course',
                ),
            ],
            database_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(
                    model_name='preschedule',
                    old_name='curriculum_type_pre',
                    new_name='student_group_name_pre',
                ),
            ],
            database_operations=[],
        ),

        # --- AddField: section_pre มีอยู่แล้วใน DB -> อัปเดต state อย่างเดียว ---
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='preschedule',
                    name='section_pre',
                    field=models.CharField(max_length=10, default=''),
                ),
            ],
            database_operations=[],
        ),

        # --- AddField: hours_activity มีอยู่แล้วใน DB -> อัปเดต state อย่างเดียว ---
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='weekactivity',
                    name='hours_activity',
                    field=models.IntegerField(default=0),
                ),
            ],
            database_operations=[],
        ),

        # --- AlterField: อันนี้ให้รันจริง (ปรับ max_length ของ day_of_week ถ้ายังไม่ได้ปรับ) ---
        migrations.AlterField(
            model_name='timeslot',
            name='day_of_week',
            field=models.CharField(
                choices=[
                    ('จันทร์', 'จันทร์'),
                    ('อังคาร', 'อังคาร'),
                    ('พุธ', 'พุธ'),
                    ('พฤหัสบดี', 'พฤหัสบดี'),
                    ('ศุกร์', 'ศุกร์'),
                    ('เสาร์', 'เสาร์'),
                    ('อาทิตย์', 'อาทิตย์'),
                ],
                max_length=20,
            ),
        ),
    ]
