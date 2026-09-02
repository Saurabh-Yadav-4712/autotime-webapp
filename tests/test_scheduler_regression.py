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

def test_swap_over_move_local_minimum():
    """
    Simulates a local minimum:
    Class A: U1 (slot 0), FREE (slot 1), U2 (slot 2)
    Class B: U3 (slot 1)

    U2 shares a teacher with U3.
    A simple move of U2 to slot 1 fails because the teacher is busy with U3.
    A swap of U2 and U3 allows U2 into slot 1 and U3 into slot 2, closing the gap for Class A.
    """
    slots = [TimeSlot("Mon", i, f"{9+i:02d}:00", f"{10+i:02d}:00") for i in range(3)]
    engine = TimetableEngine(time_slots=slots, days=["Mon"])
    state = GlobalState()
    state.teacher_max_hours = {"T1": 10, "T2": 10}

    u1 = SessionOccurrence("u1", 1, "SubA", "T1", ["ClassA"], 1, [], False)
    u2 = SessionOccurrence("u2", 2, "SubB", "T2", ["ClassA"], 1, [], False)
    u3 = SessionOccurrence("u3", 3, "SubC", "T2", ["ClassB"], 1, [], False)
    u4 = SessionOccurrence("u4", 4, "SubD", "T1", ["ClassC"], 1, [], False)

    # Assign them into a gap configuration manually
    state.assign("T1", ["ClassA"], "Mon", 0, 1)
    u1.assigned_slot = TimeSlot("Mon", 0, "09:00", "10:00")

    state.assign("T2", ["ClassA"], "Mon", 2, 1)
    u2.assigned_slot = TimeSlot("Mon", 2, "11:00", "12:00")

    state.assign("T2", ["ClassB"], "Mon", 1, 1)
    u3.assigned_slot = TimeSlot("Mon", 1, "10:00", "11:00")

    state.assign("T1", ["ClassC"], "Mon", 1, 1)
    u4.assigned_slot = TimeSlot("Mon", 1, "10:00", "11:00")

    units = [u1, u2, u3, u4]

    c_gaps_before, _ = engine._calculate_exact_gaps(state)
    assert c_gaps_before == 1, "Should have 1 class internal gap initially"

    # Run optimizer
    engine._optimize(units, state)

    c_gaps_after, _ = engine._calculate_exact_gaps(state)

    print("\n--- Final Slots ---")
    for u in units:
        print(f"{u.id}: {u.assigned_slot.idx}")

    # Verify the optimizer swapped them
    assert c_gaps_after == 0, "Swap failed to resolve the local minimum class gap"

    # Verify hard constraints
    v_ok, v_msg = engine._validate_timetable(units, state)
    assert v_ok, f"Validation failed after swap: {v_msg}"
    assert u1.assigned_slot.idx == 1 or u2.assigned_slot.idx == 1, "Either U1 or U2 should have moved to slot 1 to close the gap"

def test_swap_rollback_safety():
    """Verify that a rejected swap leaves the state exactly as it was."""
    slots = [TimeSlot("Mon", i, f"{9+i:02d}:00", f"{10+i:02d}:00") for i in range(2)]
    engine = TimetableEngine(time_slots=slots, days=["Mon"])
    state = GlobalState()

    u1 = SessionOccurrence("u1", 1, "SubA", "T1", ["ClassA"], 1, [], False)
    u2 = SessionOccurrence("u2", 2, "SubB", "T2", ["ClassB"], 1, [], False)

    state.assign("T1", ["ClassA"], "Mon", 0, 1)
    u1.assigned_slot = TimeSlot("Mon", 0, "09:00", "10:00")

    state.assign("T2", ["ClassB"], "Mon", 1, 1)
    u2.assigned_slot = TimeSlot("Mon", 1, "10:00", "11:00")

    # We will simulate the swap block manually to check rollback
    day_a, idx_a = "Mon", 0
    day_b, idx_b = "Mon", 1

    state.unassign("T1", ["ClassA"], day_a, idx_a, 1)
    state.unassign("T2", ["ClassB"], day_b, idx_b, 1)

    # Pretend valid = False or delta > 0, we must rollback
    state.assign("T1", ["ClassA"], day_a, idx_a, 1)
    state.assign("T2", ["ClassB"], day_b, idx_b, 1)

    assert "Mon" in state.teacher_busy["T1"] and 0 in state.teacher_busy["T1"]["Mon"]
    assert "Mon" in state.teacher_busy["T2"] and 1 in state.teacher_busy["T2"]["Mon"]
    assert 1 not in state.teacher_busy["T1"]["Mon"]
    assert 0 not in state.teacher_busy["T2"]["Mon"]

def test_common_subject_swap():
    """Test swapping a duration-1 common subject ensures all classes move together."""
    slots = [TimeSlot("Mon", i, f"{9+i:02d}:00", f"{10+i:02d}:00") for i in range(3)]
    engine = TimetableEngine(time_slots=slots, days=["Mon"])
    state = GlobalState()

    # Common subject across ClassA and ClassB
    u_com = SessionOccurrence("u_com", 1, "Common", "T1", ["ClassA", "ClassB"], 1, [], False)
    u_other = SessionOccurrence("u_other", 2, "Other", "T2", ["ClassC"], 1, [], False)

    state.assign("T1", ["ClassA", "ClassB"], "Mon", 0, 1)
    u_com.assigned_slot = TimeSlot("Mon", 0, "09:00", "10:00")

    state.assign("T2", ["ClassC"], "Mon", 1, 1)
    u_other.assigned_slot = TimeSlot("Mon", 1, "10:00", "11:00")

    # Do swap
    state.unassign("T1", ["ClassA", "ClassB"], "Mon", 0, 1)
    state.unassign("T2", ["ClassC"], "Mon", 1, 1)

    state.assign("T1", ["ClassA", "ClassB"], "Mon", 1, 1)
    state.assign("T2", ["ClassC"], "Mon", 0, 1)

    # Verify both classes moved together
    assert 1 in state.class_busy["ClassA"]["Mon"]
    assert 1 in state.class_busy["ClassB"]["Mon"]
    assert 0 in state.class_busy["ClassC"]["Mon"]

    # Verify no corruption
    assert 0 not in state.class_busy["ClassA"]["Mon"]
    assert 0 not in state.class_busy["ClassB"]["Mon"]
