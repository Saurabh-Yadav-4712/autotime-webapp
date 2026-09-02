from collections import namedtuple
import sys
import os
import pytest

sys.path.append(os.path.abspath("."))
from utils.timetable_helpers import build_timetable_view_model

Entry = namedtuple("Entry", ["id", "subject_name", "teacher_name", "class_id", "is_proxy"])
time_slots = [
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("12:00", "13:00"),
    ("13:00", "14:00"),
]


def run_gap_test(schedule_dict, expected_internal_gaps):
    days = ["Monday"]
    schedule = {"Monday": schedule_dict}

    view_model = build_timetable_view_model(schedule, days, time_slots)
    monday_slots = view_model[0]["slots"]

    actual_internal_gaps = sum(1 for s in monday_slots if s["status"] == "internal_gap")
    assert actual_internal_gaps == expected_internal_gaps, (
        f"Expected {expected_internal_gaps}, Got {actual_internal_gaps}"
    )
    return monday_slots


def test_internal_gap_semantics():
    # A: 09 L, 10 L, 11 F, 12 L -> internal gap = 1
    run_gap_test(
        {
            "09:00": Entry(1, "A", "T", "C", False),
            "10:00": Entry(2, "B", "T", "C", False),
            "12:00": Entry(3, "C", "T", "C", False),
        },
        1,
    )

    # B: 09 F, 10 L, 11 L, 12 L -> internal gap = 0
    run_gap_test(
        {
            "10:00": Entry(1, "A", "T", "C", False),
            "11:00": Entry(2, "B", "T", "C", False),
            "12:00": Entry(3, "C", "T", "C", False),
        },
        0,
    )

    # C: 09 L, 10 F, 11 F, 12 L -> internal gap = 2
    run_gap_test(
        {"09:00": Entry(1, "A", "T", "C", False), "12:00": Entry(3, "C", "T", "C", False)}, 2
    )


def test_screenshot_practical_case():
    """
    Test this exact screenshot-like case:
    Practical: duration = 2, start = first period (09:00, 10:00)
    Theory sessions: period 3 (11:00), period 4 (12:00), period 5 (13:00)
    Expected: class_internal_gaps = 0
    """
    slots = run_gap_test(
        {
            "09:00": Entry(1, "Operating Systems Lab", "T", "C", False),
            "10:00": Entry(1, "Operating Systems Lab", "T", "C", False),
            "11:00": Entry(2, "Theory 1", "T", "C", False),
            "12:00": Entry(3, "Theory 2", "T", "C", False),
            "13:00": Entry(4, "Theory 3", "T", "C", False),
        },
        0,
    )

    # Ensure statuses are scheduled, not free
    for s in slots:
        assert s["status"] == "occupied", (
            f"Slot {s['start_time']} should be occupied, got {s['status']}"
        )


def test_actual_real_gap():
    """
    THEORY, FREE, THEORY, THEORY, THEORY
    Must return class_internal_gaps = 1
    """
    run_gap_test(
        {
            "09:00": Entry(1, "Theory 1", "T", "C", False),
            # 10:00 is FREE
            "11:00": Entry(2, "Theory 2", "T", "C", False),
            "12:00": Entry(3, "Theory 3", "T", "C", False),
            "13:00": Entry(4, "Theory 4", "T", "C", False),
        },
        1,
    )
