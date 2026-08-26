from typing import List, Tuple
from .core import SessionOccurrence, TimeSlot

class TimetableValidator:
    """
    Independent validator to audit the global timetable before saving.
    Returns (is_valid, list_of_errors)
    """
    
    @staticmethod
    def audit(units: List[SessionOccurrence], time_slots: List[TimeSlot], teacher_available_days: dict = None) -> Tuple[bool, List[str]]:
        errors = []
        
        teacher_schedule = {} # teacher_id -> day -> set of indices
        class_schedule = {} # class_id -> day -> set of indices
        
        # Build tracking structures and check hard constraints
        for unit in units:
            if not unit.assigned_slot:
                errors.append(f"Hard Constraint Violation: {unit.subject_name} for classes {unit.target_classes} is not assigned a slot.")
                continue
                
            day = unit.assigned_slot.day
            start_idx = unit.assigned_slot.idx
            
            for i in range(unit.duration):
                idx = start_idx + i
                
                # Check bounds
                if idx >= len(time_slots):
                    errors.append(f"Hard Constraint Violation: {unit.subject_name} exceeds day bounds.")
                    continue
                    
                # Check teacher double-booking and availability
                if unit.teacher_id:
                    if idx in teacher_schedule.get(unit.teacher_id, {}).get(day, set()):
                        errors.append(f"Hard Constraint Violation: Teacher {unit.teacher_id} is double-booked on {day} at slot index {idx}.")
                        
                    if teacher_available_days and unit.teacher_id in teacher_available_days:
                        if day not in teacher_available_days[unit.teacher_id]:
                            errors.append(f"Hard Constraint Violation: Teacher {unit.teacher_id} is assigned on {day} but is not available.")
                            
                    teacher_schedule.setdefault(unit.teacher_id, {}).setdefault(day, set()).add(idx)
                    
                # Check class double-booking
                for c_id in unit.target_classes:
                    if idx in class_schedule.get(c_id, {}).get(day, set()):
                        errors.append(f"Hard Constraint Violation: Class {c_id} is double-booked on {day} at slot index {idx}.")
                    class_schedule.setdefault(c_id, {}).setdefault(day, set()).add(idx)
                    
        return len(errors) == 0, errors
