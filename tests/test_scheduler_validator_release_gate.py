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

def test_a_custom_scheduler_budget():
    config = SchedulerConfig(generation_timeout_seconds=0.123, optimization_timeout_seconds=0.456, optimization_max_iterations=7)
    engine = TimetableEngine(time_slots=get_base_slots(), days=["Mon"], scheduler_config=config)

    assert engine.max_generation_seconds == 0.123
    assert engine.max_optimization_seconds == 0.456
    assert engine.max_optimization_iterations == 7

def test_b_missing_required_occurrence():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
        duration=1, preferred_days=[], is_practical=False, assigned_slot=None
    )]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2, {"C1"})
    assert not is_valid
    assert any("is not assigned a slot" in str(e) for e in errors)

def test_c_duplicate_logical_occurrence():
    units = get_base_units()
    units.append(SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 1, "09:00", "10:00")
    ))
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2, {"C1"})
    assert not is_valid
    assert any("Duplicate logical occurrence 'U1' detected" in str(e) for e in errors)

def test_d_unknown_teacher_fails():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="UNKNOWN_TEACHER", target_classes=["C1"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
    )]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2, {"C1"})
    assert not is_valid
    assert any("Assigned Teacher UNKNOWN_TEACHER is unknown" in str(e) for e in errors)

def test_e_unknown_target_class_fails():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["UNKNOWN_CLASS"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
    )]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2, {"C1"})
    assert not is_valid
    assert any("Assigned Class UNKNOWN_CLASS is unknown" in str(e) for e in errors)

def test_f_valid_shared_common_occurrence_passes():
    units = [SessionOccurrence(
        id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1", "C2"],
        duration=1, preferred_days=[], is_practical=False,
        assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
    )]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}}, {"T1": 10}, 2, {"C1", "C2"})
    assert is_valid
    assert len(errors) == 0

def test_g_shared_occurrence_with_one_target_class_collision_fails():
    units = [
        SessionOccurrence(
            id="U1", subject_id=1, subject_name="Math", teacher_id="T1", target_classes=["C1", "C2"],
            duration=1, preferred_days=[], is_practical=False,
            assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
        ),
        SessionOccurrence(
            id="U2", subject_id=2, subject_name="Physics", teacher_id="T2", target_classes=["C2"],
            duration=1, preferred_days=[], is_practical=False,
            assigned_slot=TimeSlot("Mon", 0, "08:00", "09:00")
        )
    ]
    is_valid, errors = TimetableValidator.audit(units, get_base_slots(), ["Mon", "Tue"], {"T1": {"Mon", "Tue"}, "T2": {"Mon", "Tue"}}, {"T1": 10, "T2": 10}, 2, {"C1", "C2"})
    assert not is_valid
    assert any("Class C2 is double-booked" in str(e) for e in errors)
