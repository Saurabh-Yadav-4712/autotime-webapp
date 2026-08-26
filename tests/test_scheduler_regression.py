from utils.scheduler.engine import TimetableEngine
from utils.scheduler.core import GlobalState, SessionOccurrence, TimeSlot

def test_shared_teacher_multi_course():
    slots = [TimeSlot("Mon", i, f"{9+i:02d}:00", f"{10+i:02d}:00") for i in range(5)]
    days = ["Mon"]
    state = GlobalState()
    state.teacher_max_hours = {"T1": 10, "T2": 10}
    
    # 3 courses, T1 is shared across all 3
    units = [
        SessionOccurrence("u1", 1, "SubA", "T1", ["CourseA"], 1, [], False),
        SessionOccurrence("u2", 2, "SubB", "T1", ["CourseB"], 1, [], False),
        SessionOccurrence("u3", 3, "SubC", "T1", ["CourseC"], 1, [], False),
        SessionOccurrence("u4", 4, "SubD", "T2", ["CourseA"], 1, [], False),
        SessionOccurrence("u5", 5, "SubE", "T2", ["CourseB"], 1, [], False),
    ]
    
    engine = TimetableEngine(time_slots=slots, days=days)
    success, sched, msg, stats, diag = engine.generate(units, state)
    
    assert success == True, "Failed to schedule shared teacher across 3 courses"
    assert len(sched) == 5
    
    print("\n--- Scheduler Regression Stats ---")
    for k, v in stats.items():
        print(f"{k}: {v}")
    
    # Verify no overlaps for T1
    t1_slots = [u.assigned_slot.start_time for u in sched if u.teacher_id == "T1"]
    assert len(t1_slots) == len(set(t1_slots)), "Teacher T1 has overlapping sessions!"

if __name__ == '__main__':
    test_shared_teacher_multi_course()
