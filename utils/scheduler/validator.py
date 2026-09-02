from typing import List, Tuple
from .core import SessionOccurrence, TimeSlot

class TimetableValidator:
    """
    Independent validator to audit the global timetable before saving.
    Returns (is_valid, list_of_errors)
    """

    @staticmethod
    def audit(
        units: List[SessionOccurrence],
        time_slots: List[TimeSlot],
        working_days: List[str],
        teacher_available_days: dict,
        teacher_max_hours: dict,
        lunch_after: int,
        valid_classes: set = None
    ) -> Tuple[bool, List[str]]:
        errors = []

        teacher_schedule = {}  # teacher_id -> day -> set of indices
        class_schedule = {}  # class_id -> day -> set of indices
        teacher_workload = {}  # teacher_id -> total_hours
        seen_unit_ids = set()

        # Group by session_group_id to check shared logic if applicable
        # Actually in this model, SessionOccurrence itself can have multiple target_classes.
        # target_classes handles shared sessions.

        # First pass: Check assignments, bounds, working days, continuity, double booking
        for unit in units:
            if unit.id in seen_unit_ids:
                errors.append(f"Hard Constraint Violation: Duplicate logical occurrence '{unit.id}' detected.")
            seen_unit_ids.add(unit.id)

            if not unit.assigned_slot:
                errors.append(
                    f"Hard Constraint Violation: {unit.subject_name} for classes {unit.target_classes} is not assigned a slot."
                )
                continue

            day = unit.assigned_slot.day
            start_idx = unit.assigned_slot.idx

            if day not in working_days:
                errors.append(f"Hard Constraint Violation: {unit.subject_name} assigned to {day}, which is not a configured working day.")

            # Continuity / Bounds / Lunch
            if start_idx < 0 or start_idx + unit.duration > len(time_slots):
                errors.append(f"Hard Constraint Violation: {unit.subject_name} exceeds day bounds.")
                continue

            if unit.duration > 1:
                # Practical continuity crossing lunch boundary
                if start_idx < lunch_after and (start_idx + unit.duration) > lunch_after:
                    errors.append(f"Hard Constraint Violation: {unit.subject_name} (duration {unit.duration}) crosses the lunch boundary at period {lunch_after}.")

            for i in range(unit.duration):
                idx = start_idx + i

                # Teacher constraints
                if unit.teacher_id:
                    if unit.teacher_id not in teacher_max_hours:
                        errors.append(f"Hard Constraint Violation: Assigned Teacher {unit.teacher_id} is unknown.")

                    if idx in teacher_schedule.get(unit.teacher_id, {}).get(day, set()):
                        errors.append(
                            f"Hard Constraint Violation: Teacher {unit.teacher_id} is double-booked on {day} at slot index {idx}."
                        )

                    if teacher_available_days and unit.teacher_id in teacher_available_days:
                        if day not in teacher_available_days[unit.teacher_id]:
                            errors.append(
                                f"Hard Constraint Violation: Teacher {unit.teacher_id} is assigned on {day} but is not available."
                            )

                    teacher_schedule.setdefault(unit.teacher_id, {}).setdefault(day, set()).add(idx)
                    teacher_workload[unit.teacher_id] = teacher_workload.get(unit.teacher_id, 0) + 1

                # Class constraints
                for c_id in unit.target_classes:
                    if valid_classes is not None and c_id not in valid_classes:
                        errors.append(f"Hard Constraint Violation: Assigned Class {c_id} is unknown.")

                    if idx in class_schedule.get(c_id, {}).get(day, set()):
                        errors.append(
                            f"Hard Constraint Violation: Class {c_id} is double-booked on {day} at slot index {idx}."
                        )
                    class_schedule.setdefault(c_id, {}).setdefault(day, set()).add(idx)

        # Second pass: Check workload
        for t_id, hours in teacher_workload.items():
            if t_id in teacher_max_hours:
                if hours > teacher_max_hours[t_id]:
                    errors.append(f"Hard Constraint Violation: Teacher {t_id} exceeds max workload ({hours} > {teacher_max_hours[t_id]}).")

        return len(errors) == 0, errors
