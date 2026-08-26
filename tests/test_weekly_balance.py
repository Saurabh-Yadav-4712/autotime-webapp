import pytest
from utils.scheduler.engine import TimetableEngine, GlobalState, SessionOccurrence, TimeSlot

class MockEngine(TimetableEngine):
    def __init__(self, working_days=5, max_lectures=5):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][:working_days]
        slots = [TimeSlot(day="", idx=i, start_time=f"{8+i}:00", end_time=f"{9+i}:00") for i in range(max_lectures)]
        super().__init__(slots, days)

def test_case_c_lexicographic_balance_metric():
    # Case C: Same range, different distribution.
    # [5,5,5,3,3] vs [5,5,4,4,3] -> Ideal for 21 is [5,4,4,4,4]
    engine = MockEngine(working_days=5, max_lectures=5)
    state = GlobalState()

    # We can test the _calculate_class_balance logic directly by mocking state.class_busy
    state.class_busy["C1"] = {
        "Monday": set(range(5)),
        "Tuesday": set(range(5)),
        "Wednesday": set(range(5)),
        "Thursday": set(range(3)),
        "Friday": set(range(3))
    }

    score1 = engine._calculate_class_balance(state)

    state.class_busy["C1"] = {
        "Monday": set(range(5)),
        "Tuesday": set(range(5)),
        "Wednesday": set(range(4)),
        "Thursday": set(range(4)),
        "Friday": set(range(3))
    }

    score2 = engine._calculate_class_balance(state)

    # Both have range 2, but [5,5,4,4,3] should have a lower penalty than [5,5,5,3,3] compared to [5,4,4,4,4]
    # [5,5,5,3,3] vs [5,4,4,4,4] -> abs(5-5)+abs(5-4)+abs(5-4)+abs(3-4)+abs(3-4) = 0 + 1 + 1 + 1 + 1 = 4
    # [5,5,4,4,3] vs [5,4,4,4,4] -> abs(5-5)+abs(5-4)+abs(4-4)+abs(4-4)+abs(3-4) = 0 + 1 + 0 + 0 + 1 = 2

    assert score2 < score1
    assert score1 == 4
    assert score2 == 2

def test_case_e_practical_load():
    engine = MockEngine()
    state = GlobalState()

    unit = SessionOccurrence("1", 1, "Sub1", "T1", ["C1"], 2, [], True)
    state.assign("T1", ["C1"], "Monday", 0, 2)

    bal = engine._calculate_class_balance(state, ["C1"])
    # 2 periods / 5 days -> ideal [1, 1, 0, 0, 0]
    # actual [2, 0, 0, 0, 0]
    # Penalty: abs(2-1) + abs(0-1) + 0 + 0 + 0 = 2
    assert bal == 2

    # Verify exact occupied counts
    counts = [len(state.class_busy.get("C1", {}).get(d, set())) for d in engine.days]
    assert counts[0] == 2
    assert sum(counts) == 2

def test_case_f_common_subject_load():
    engine = MockEngine()
    state = GlobalState()

    # Common subject targeting C1 and C2
    state.assign("T1", ["C1", "C2"], "Monday", 0, 1)

    c1_bal = engine._calculate_class_balance(state, ["C1"])
    c2_bal = engine._calculate_class_balance(state, ["C2"])

    # 1 period / 5 days -> ideal [1, 0, 0, 0, 0]
    # actual [1, 0, 0, 0, 0]
    # Penalty: 0
    assert c1_bal == 0
    assert c2_bal == 0

def test_case_a_and_b_optimization():
    # Case A: 21 periods
    engine = MockEngine()
    state = GlobalState()

    units = []
    # Create 21 individual units
    for i in range(21):
        u = SessionOccurrence(str(i), i, f"Sub{i}", "T1", ["C1"], 1, [], False)
        # Assign tightly to first 4 days (5 each) and 1 on Friday
        if i < 5:
            d = "Monday"
            idx = i
        elif i < 10:
            d = "Tuesday"
            idx = i - 5
        elif i < 15:
            d = "Wednesday"
            idx = i - 10
        elif i < 20:
            d = "Thursday"
            idx = i - 15
        else:
            d = "Friday"
            idx = 0

        u.assigned_slot = TimeSlot(day=d, idx=idx, start_time="", end_time="")
        state.assign("T1", ["C1"], d, idx, 1)
        units.append(u)

    initial_score = engine._calculate_global_score(state)
    assert initial_score[1] == 6 # Balance penalty for [5,5,5,5,1] is 6

    # optimize
    engine._optimize(units, state)

    final_score = engine._calculate_global_score(state)
    assert final_score[1] == 0 # Balance penalty should reach 0 -> [5,4,4,4,4]

def test_case_d_teacher_override():
    engine = MockEngine()
    state = GlobalState()

    # Teacher is ONLY available Monday and Tuesday (restrict busy array)
    state.teacher_max_hours["T1"] = 10

    # 10 units for C1 and T1, which will force 5 on Mon, 5 on Tue.
    # If the balance optimizer tried to move them to Wed, it would violate availability.
    # We simulate availability by marking T1 busy on Wed/Thu/Fri for all slots.
    for d in ["Wednesday", "Thursday", "Friday"]:
        for i in range(5):
            state.assign("T1", ["DUMMY"], d, i, 1)

    units = []
    for i in range(10):
        u = SessionOccurrence(str(i), i, f"Sub{i}", "T1", ["C1"], 1, [], False)
        if i < 5:
            d = "Monday"
            idx = i
        else:
            d = "Tuesday"
            idx = i - 5

        u.assigned_slot = TimeSlot(day=d, idx=idx, start_time="", end_time="")
        state.assign("T1", ["C1"], d, idx, 1)
        units.append(u)

    initial_score = engine._calculate_global_score(state)

    engine._optimize(units, state)

    final_score = engine._calculate_global_score(state)

    # Because T1 is completely blocked W/Th/F, it cannot move the units.
    # The balance should stay identical, and validation must pass.
    assert final_score[1] == initial_score[1]

    v_ok, _ = engine._validate_timetable(units, state)
    assert v_ok is True
