from collections import namedtuple
import sys
import os

sys.path.append(os.path.abspath('.'))
from utils.timetable_helpers import build_timetable_view_model

Entry = namedtuple('Entry', ['id', 'subject_name', 'teacher_name', 'class_id', 'is_proxy'])
time_slots = [("09:00", "10:00"), ("10:00", "11:00"), ("11:00", "12:00"), ("12:00", "13:00")]

def run_test(name, schedule_dict, expected_internal_gaps):
    days = ["Monday"]
    schedule = {"Monday": schedule_dict}
    
    view_model = build_timetable_view_model(schedule, days, time_slots)
    monday_slots = view_model[0]["slots"]
    
    actual_internal_gaps = sum(1 for s in monday_slots if s["status"] == "internal_gap")
    
    print(f"Test {name}: Expected {expected_internal_gaps}, Got {actual_internal_gaps}")
    assert actual_internal_gaps == expected_internal_gaps, f"Failed {name}!"
    return monday_slots

if __name__ == '__main__':
    # A: 09 L, 10 L, 11 F, 12 L -> internal gap = 1
    run_test("A", {
        "09:00": Entry(1, "A", "T", "C", False),
        "10:00": Entry(2, "B", "T", "C", False),
        "12:00": Entry(3, "C", "T", "C", False)
    }, 1)
    
    # B: 09 F, 10 L, 11 L, 12 L -> internal gap = 0
    run_test("B", {
        "10:00": Entry(1, "A", "T", "C", False),
        "11:00": Entry(2, "B", "T", "C", False),
        "12:00": Entry(3, "C", "T", "C", False)
    }, 0)
    
    # C: 09 L, 10 F, 11 F, 12 L -> internal gap = 2
    run_test("C", {
        "09:00": Entry(1, "A", "T", "C", False),
        "12:00": Entry(3, "C", "T", "C", False)
    }, 2)
    
    # D: 09 L, 10 L, 11 F, 12 F -> internal gap = 0
    run_test("D", {
        "09:00": Entry(1, "A", "T", "C", False),
        "10:00": Entry(3, "C", "T", "C", False)
    }, 0)
    
    # E: 09 F, 10 F, 11 L, 12 L -> internal gap = 0
    run_test("E", {
        "11:00": Entry(1, "A", "T", "C", False),
        "12:00": Entry(3, "C", "T", "C", False)
    }, 0)
    
    print("All Gap Semantics Tests Passed!")
