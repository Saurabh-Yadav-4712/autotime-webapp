def build_timetable_view_model(schedule, days, time_slots):
    """
    Transforms the legacy timetable schedule dictionary into a unified,
    presentation-ready View Model with calculated gap semantics.

    Returns:
    [
        {
            "day": "Monday",
            "slots": [
                {
                    "status": "occupied" | "proxy" | "internal_gap" | "edge_free",
                    "id": 1,
                    "subject": "Math",
                    "teacher": "John",
                    "course": "CS-1",
                    "start_time": "09:00"
                }, ...
            ]
        }, ...
    ]
    """
    days_data = []

    for day in days:
        day_schedule = schedule.get(day, {})
        slots_data = []

        # Calculate bounds to determine internal vs edge gaps
        first_occupied_idx = -1
        last_occupied_idx = -1

        for idx, slot in enumerate(time_slots):
            start_time = slot[0]
            if start_time in day_schedule:
                if first_occupied_idx == -1:
                    first_occupied_idx = idx
                last_occupied_idx = idx

        for idx, slot in enumerate(time_slots):
            start_time = slot[0]
            slot_model = {
                "start_time": start_time,
                "status": "edge_free",
                "id": None,
                "subject": "",
                "teacher": "",
                "course": "",
            }

            if start_time in day_schedule:
                entry = day_schedule[start_time]
                slot_model["id"] = entry.id
                slot_model["subject"] = entry.subject_name
                slot_model["teacher"] = entry.teacher_name
                slot_model["course"] = entry.class_id

                if getattr(entry, "is_proxy", False):
                    slot_model["status"] = "proxy"
                else:
                    slot_model["status"] = "occupied"

                # Optionally add practical distinction if data supports it
                # if "Prac" in entry.subject_name or getattr(entry, 'is_practical', False):
                #     slot_model["status"] = "practical"

            else:
                # Determine gap type
                if first_occupied_idx != -1 and first_occupied_idx < idx < last_occupied_idx:
                    slot_model["status"] = "internal_gap"
                else:
                    slot_model["status"] = "edge_free"

            slots_data.append(slot_model)

        days_data.append({"day": day, "slots": slots_data})

    return days_data
