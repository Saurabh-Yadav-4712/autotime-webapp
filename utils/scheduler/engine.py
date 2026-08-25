import random
import copy
from typing import List, Dict, Set, Tuple, Optional
from .core import TimeSlot, SessionOccurrence, GlobalState

class TimetableEngine:
    def __init__(self, time_slots: List[TimeSlot], days: List[str], max_iterations=1000, seed=None):
        self.time_slots = time_slots
        self.days = days
        self.max_iterations = max_iterations
        if seed is not None:
            random.seed(seed)
        
        self.stats = {
            "candidates_evaluated": 0,
            "forward_check_failures": 0,
            "backtracks": 0,
            "backjumps": 0,
            "max_depth": 0,
            "optimization_moves_attempted": 0,
            "optimization_moves_accepted": 0
        }
            
    def generate(self, units: List[SessionOccurrence], initial_state: GlobalState) -> Tuple[bool, List[SessionOccurrence], str, dict]:
        state = copy.deepcopy(initial_state)
        
        def calculate_mcf_score(unit: SessionOccurrence) -> int:
            score = unit.duration * 100
            if unit.is_practical: score += 50
            if len(unit.target_classes) > 1: score += 200
            return score
            
        units.sort(key=calculate_mcf_score, reverse=True)
        
        success, scheduled_units, msg = self._solve(units, state, 0)
        
        if success:
            self._optimize(scheduled_units, state)
            return True, scheduled_units, "Generation successful.", self.stats
        else:
            return False, [], msg, self.stats
            
    def _get_valid_candidates(self, unit: SessionOccurrence, state: GlobalState) -> List[Tuple[str, int]]:
        candidates = []
        for day in self.days:
            if unit.preferred_days and day not in unit.preferred_days:
                continue
                
            max_start_idx = len(self.time_slots) - unit.duration
            for idx in range(max_start_idx + 1):
                if state.is_free(unit.teacher_id, unit.target_classes, day, idx, unit.duration):
                    candidates.append((day, idx))
        return candidates

    def _evaluate_candidate(self, unit: SessionOccurrence, state: GlobalState, day: str, idx: int, scheduled_units: List[SessionOccurrence]) -> int:
        self.stats["candidates_evaluated"] += 1
        score = 0
        
        def class_has_class(c_id, d, i):
            return i in state.class_busy.get(c_id, {}).get(d, set())
            
        def teacher_has_class(t_id, d, i):
            if not t_id: return False
            return i in state.teacher_busy.get(t_id, {}).get(d, set())

        for c_id in unit.target_classes:
            adj_before = class_has_class(c_id, day, idx - 1) if idx > 0 else False
            adj_after = class_has_class(c_id, day, idx + unit.duration) if idx + unit.duration < len(self.time_slots) else False
            
            has_earlier = any(class_has_class(c_id, day, i) for i in range(idx))
            has_later = any(class_has_class(c_id, day, i) for i in range(idx + unit.duration, len(self.time_slots)))
            
            # Adjacency Bonus (encourages packing)
            if adj_before: score += 20
            if adj_after: score += 20
            
            # Internal Gap Penalty
            if has_earlier and not adj_before: score -= 100
            if has_later and not adj_after: score -= 100

        if unit.teacher_id:
            t_adj_before = teacher_has_class(unit.teacher_id, day, idx - 1) if idx > 0 else False
            t_adj_after = teacher_has_class(unit.teacher_id, day, idx + unit.duration) if idx + unit.duration < len(self.time_slots) else False
            
            t_has_earlier = any(teacher_has_class(unit.teacher_id, day, i) for i in range(idx))
            t_has_later = any(teacher_has_class(unit.teacher_id, day, i) for i in range(idx + unit.duration, len(self.time_slots)))
            
            # Teacher Adjacency Bonus
            if t_adj_before: score += 10
            if t_adj_after: score += 10
            
            # Teacher Internal Gap Penalty
            if t_has_earlier and not t_adj_before: score -= 50
            if t_has_later and not t_adj_after: score -= 50
            
        # Subject Distribution Penalty (prevent same subject twice on same day unless forced)
        for su in scheduled_units:
            if su.subject_id == unit.subject_id and su.assigned_slot and su.assigned_slot.day == day:
                if any(c in su.target_classes for c in unit.target_classes):
                    score -= 200 # Heavy penalty for poor weekly distribution
                    break

        return score

    def _solve(self, units: List[SessionOccurrence], state: GlobalState, depth: int) -> Tuple[bool, List[SessionOccurrence], str]:
        if depth > self.stats["max_depth"]:
            self.stats["max_depth"] = depth
            
        if depth >= len(units):
            return True, units, ""
            
        unit = units[depth]
        candidates = self._get_valid_candidates(unit, state)
        
        if not candidates:
            msg = f"Failed at {unit.subject_name}. Teacher: {unit.teacher_id}. No valid slots left."
            return False, [], msg
            
        scored_candidates = []
        for day, idx in candidates:
            score = self._evaluate_candidate(unit, state, day, idx, units[:depth])
            scored_candidates.append((score, day, idx))
            
        # Sort candidates strictly by score (highest first)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        for score, day, idx in scored_candidates:
            state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            time_slot_obj = next((ts for ts in self.time_slots if ts.idx == idx), None)
            unit.assigned_slot = TimeSlot(day=day, idx=idx, start_time=time_slot_obj.start_time, end_time=self.time_slots[idx + unit.duration - 1].end_time)
            
            forward_check_ok = True
            for future_unit in units[depth+1:]:
                if future_unit.teacher_id == unit.teacher_id or any(c in future_unit.target_classes for c in unit.target_classes):
                    if not self._get_valid_candidates(future_unit, state):
                        forward_check_ok = False
                        self.stats["forward_check_failures"] += 1
                        break
            
            if forward_check_ok:
                success, result_units, msg = self._solve(units, state, depth + 1)
                if success:
                    return True, result_units, ""
                else:
                    self.stats["backtracks"] += 1
                    
            unit.assigned_slot = None
            state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            
        self.stats["backjumps"] += 1
        msg = f"Backtracking exhausted for {unit.subject_name}. All {len(candidates)} candidates led to future failures."
        return False, [], msg
        
    def _optimize(self, units: List[SessionOccurrence], state: GlobalState):
        def calculate_global_gap_score() -> int:
            total_penalty = 0
            for c_id, days_data in state.class_busy.items():
                for day, slots in days_data.items():
                    if not slots: continue
                    indices = sorted(list(slots))
                    span = indices[-1] - indices[0] + 1
                    gaps = span - len(indices)
                    total_penalty += gaps * 100
                    
            for t_id, days_data in state.teacher_busy.items():
                for day, slots in days_data.items():
                    if not slots: continue
                    indices = sorted(list(slots))
                    span = indices[-1] - indices[0] + 1
                    gaps = span - len(indices)
                    total_penalty += gaps * 50
            return total_penalty

        current_penalty = calculate_global_gap_score()
        made_changes = True
        passes = 0
        
        while made_changes and passes < 5:
            made_changes = False
            passes += 1
            
            for unit in units:
                if not unit.assigned_slot: continue
                self.stats["optimization_moves_attempted"] += 1
                
                original_day = unit.assigned_slot.day
                original_idx = unit.assigned_slot.idx
                
                state.unassign(unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration)
                
                candidates = self._get_valid_candidates(unit, state)
                
                best_penalty = current_penalty
                best_move = None
                
                for day, idx in candidates:
                    if day == original_day and idx == original_idx: continue
                    
                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    new_penalty = calculate_global_gap_score()
                    if new_penalty < best_penalty:
                        best_penalty = new_penalty
                        best_move = (day, idx)
                    state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                
                if best_move and best_penalty < current_penalty:
                    day, idx = best_move
                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    time_slot_obj = next((ts for ts in self.time_slots if ts.idx == idx), None)
                    unit.assigned_slot = TimeSlot(day=day, idx=idx, start_time=time_slot_obj.start_time, end_time=self.time_slots[idx + unit.duration - 1].end_time)
                    current_penalty = best_penalty
                    made_changes = True
                    self.stats["optimization_moves_accepted"] += 1
                else:
                    state.assign(unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration)
