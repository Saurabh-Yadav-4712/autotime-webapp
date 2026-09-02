import pytest
from utils.scheduler.core import SessionOccurrence, TimeSlot, SchedulerConfig, GlobalState
from utils.scheduler.validator import TimetableValidator
from utils.scheduler.engine import TimetableEngine
from utils.scheduler.diagnostics import ReasonCodes

def get_base_units():
    return [
        SessionOccurrence(
            id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
            duration=1, preferred_days=[], is_practical=False,
            assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
        )
    ]

def get_base_slots():
    return [
        TimeSlot("Mon", 0, "08:00", "09:00"),
        TimeSlot("Mon", 1, "09:00", "10:00"),
        TimeSlot("Mon", 2, "10:00", "11:00"),
        TimeSlot("Tue", 0, "08:00", "09:00"),
    ]

def test_1_validator_catches_teacher_collision():
    units = get_base_units()
    units.append(SessionOccurrence(
        id="U2", subject_id=2, subject_name="Physics", teacher_id="T1", target_classes=["C2"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
    ))
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("Teacher T1 is double-booked" in str(e) for e in errors)

def test_2_validator_catches_class_collision():
    units = get_base_units()
    units.append(SessionOccurrence(
        id="U2", subject_id=2, subject_name="Physics", teacher_id="T2", target_classes=["C1"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
    ))
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}, "T2": {"Mon", "Tue"}}, {"T1": 10, "T2": 10}, 2)
    assert not is_valid
    assert any("Class C1 is double-booked" in str(e) for e in errors)

def test_3_validator_catches_unavailable_teacher_day():
    units = get_base_units() # T1 on Mon
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Tue"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("Teacher T1 is assigned on Mon but is not available" in str(e) for e in errors)

def test_4_validator_catches_max_workload_violation():
    units = get_base_units() # duration 1
    units.append(SessionOccurrence(
        id="U2", subject_id=2, subject_name="Physics", teacher_id="T1", target_classes=["C2"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 1, "09:00", "10:00")
    ))
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 1}, 2)
    assert not is_valid
    assert any("exceeds max workload (2 > 1)" in str(e) for e in errors)

def test_5_validator_catches_invalid_configured_working_day():
    units = get_base_units() # Mon
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Tue", "Wed"], {"T1": {"Mon", "Tue", "Wed"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("which is not a configured working day" in str(e) for e in errors)

def test_6_validator_catches_practical_lunch_crossing():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
        duration=2, preferred_days=[], is_practical=True,
        assigned_slot=TimeSlot("Mon", 1, "09:00", "10:00")
    )]
    # lunch_after = 2, meaning indices 0,1 are before lunch. A session at idx=1 duration 2 spans 1 and 2.
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("crosses the lunch boundary" in str(e) for e in errors)

def test_7_validator_catches_invalid_practical_duration_continuity():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
        duration=2, preferred_days=[], is_practical=True,
        assigned_slot=TimeSlot("Mon", 3, "11:00", "12:00")
    )]
    # starts at 3, duration 2 -> 3 and 4. but get_base_slots only has 4 slots (idx 0 to 3). So idx 4 is out of bounds.
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("exceeds day bounds" in str(e) for e in errors)

def test_8_validator_catches_missing_occurrence():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=None
    )]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2)
    assert not is_valid
    assert any("is not assigned a slot" in str(e) for e in errors)

def test_9_valid_known_timetable_passes_validator():
    units = get_base_units()
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2)
    assert is_valid
    assert len(errors) == 0

def test_10_timeout_reason():
    # Force timeout
    engine = TimetableEngine(time_slots=get_base_slots(), days=["Mon"], lunch_after=2)
    engine.max_generation_seconds = 0.00001

    state = GlobalState()
    state.teacher_max_hours["T1"] = 10
    state.teacher_available_days["T1"] = {"Mon"}

    units = [
        SessionOccurrence(id=f"U{i}", subject_id=i, subject_name="Math", teacher_id="T1", target_classes=["C1"], duration=1, preferred_days=[], is_practical=False)
        for i in range(100)
    ]
    engine._presolve = lambda u, s: None
    success, sched, msg, stats, diag = engine.generate(units, state)
    assert not success
    assert diag.reason_code == ReasonCodes.SEARCH_TIMEOUT
    assert "exceeded its configured time budget" in diag.primary_bottleneck

def test_11_impossible_reason():
    engine = TimetableEngine(time_slots=get_base_slots()[:1], days=["Mon"], lunch_after=2) # 1 slot total
    state = GlobalState()
    state.teacher_max_hours["T1"] = 10
    units = [
        SessionOccurrence(id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"], duration=1, preferred_days=[], is_practical=False),
        SessionOccurrence(id="U2", subject_id=2, subject_name="Physics", teacher_id="T1", target_classes=["C1"], duration=1, preferred_days=[], is_practical=False)
    ] # 2 units, 1 slot -> Impossible
    engine._presolve = lambda u, s: None
    success, sched, msg, stats, diag = engine.generate(units, state)
    assert not success
    assert diag.reason_code == ReasonCodes.NO_FEASIBLE_ASSIGNMENT
    assert "exceeded its configured time budget" not in diag.primary_bottleneck

def test_12_scheduler_api_compatibility():
    import inspect
    sig = inspect.signature(TimetableEngine.generate)
    assert list(sig.parameters.keys()) == ['self', 'units', 'state']

def test_13_output_contract():
    engine = TimetableEngine(time_slots=get_base_slots(), days=["Mon"], lunch_after=2)
    state = GlobalState()
    success, sched, msg, stats, diag = engine.generate([], state) # empty units
    assert isinstance(success, bool)
    assert isinstance(sched, list)
    assert isinstance(msg, str)
    assert isinstance(stats, dict)
    assert diag.status == "SUCCESS"

def test_14_dynamic_working_days():
    engine = TimetableEngine(time_slots=get_base_slots(), days=["Sun"], lunch_after=2)
    state = GlobalState()
    state.teacher_max_hours["T1"] = 10
    state.teacher_available_days["T1"] = {"Sun"}
    units = [
        SessionOccurrence(id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"], duration=1, preferred_days=[], is_practical=False)
    ]
    success, sched, msg, stats, diag = engine.generate(units, state)
    assert success
    assert sched[0].assigned_slot.day == "Sun"

def test_15_lunch_position_configuration():
    # lunch_after = 1
    engine = TimetableEngine(time_slots=get_base_slots(), days=["Mon"], lunch_after=1)
    state = GlobalState()
    state.teacher_max_hours["T1"] = 10
    state.teacher_available_days["T1"] = {"Mon"}
    units = [
        SessionOccurrence(id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"], duration=2, preferred_days=[], is_practical=True)
    ]
    success, sched, msg, stats, diag = engine.generate(units, state)
    assert success
    # Must be scheduled at idx=1, because idx=0 crosses lunch_after=1
    assert sched[0].assigned_slot.idx == 1
