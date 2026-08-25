import time
import math
from typing import List, Tuple, Dict, Set
import collections

from utils.scheduler.core import TimeSlot, SessionOccurrence, GlobalState

class TimetableEngine:
    def __init__(self, time_slots: List[TimeSlot], days: List[str], max_iterations=1000, seed=None):
        self.time_slots = time_slots
        self.days = days
        self.max_iterations = max_iterations
        self.seed = seed
        self.stats = {
            "candidates_evaluated": 0,
            "forward_check_calls": 0,
            "forward_check_failures": 0,
            "backtracks": 0,
            "backjumps": 0,
            "max_depth": 0,
            "optimization_attempts": 0,
            "optimization_accepted": 0,
            "feasibility_time": 0.0,
            "optimization_time": 0.0,
            "validation_time": 0.0,
            "total_time": 0.0
        }
        self.domains = {}
        self.teacher_deps = collections.defaultdict(list)
        self.class_deps = collections.defaultdict(list)
        
        self.max_generation_seconds = 4.0
        self.max_optimization_seconds = 2.0
        self.max_optimization_iterations = 3
        
        self.start_time = 0.0

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
            
            if adj_before or adj_after:
                score += 50
            else:
                score -= 30
                
        if unit.teacher_id:
            adj_before_t = teacher_has_class(unit.teacher_id, day, idx - 1) if idx > 0 else False
            adj_after_t = teacher_has_class(unit.teacher_id, day, idx + unit.duration) if idx + unit.duration < len(self.time_slots) else False
            
            if adj_before_t or adj_after_t:
                score += 30
            else:
                score -= 20
                
        # Subject distribution penalty
        same_day_count = 0
        for s_unit in scheduled_units:
            if s_unit.subject_id == unit.subject_id and s_unit.assigned_slot and s_unit.assigned_slot.day == day:
                same_day_count += 1
                
        if same_day_count > 0:
            score -= 200

        return score

    def _forward_check_prune(self, assigned_unit: SessionOccurrence, state: GlobalState):
        self.stats["forward_check_calls"] += 1
        pruned_history = []
        affected_units = {}
        
        if assigned_unit.teacher_id:
            for f_u in self.teacher_deps[assigned_unit.teacher_id]: affected_units[f_u.id] = f_u
        for c_id in assigned_unit.target_classes:
            for f_u in self.class_deps[c_id]: affected_units[f_u.id] = f_u
            
        for f_unit in affected_units.values():
            if f_unit.assigned_slot is not None:
                continue
                
            new_domain = []
            pruned_for_this_unit = []
            
            for c_day, c_idx in self.domains[f_unit.id]:
                if not state.is_free(f_unit.teacher_id, f_unit.target_classes, c_day, c_idx, f_unit.duration):
                    pruned_for_this_unit.append((c_day, c_idx))
                else:
                    new_domain.append((c_day, c_idx))
                    
            if not new_domain:
                # Early failure: restore everything pruned so far in this forward check
                for p_u_id, p_slots in pruned_history:
                    self.domains[p_u_id].extend(p_slots)
                self.domains[f_unit.id].extend(pruned_for_this_unit)
                self.stats["forward_check_failures"] += 1
                return False, []
                
            if pruned_for_this_unit:
                pruned_history.append((f_unit.id, pruned_for_this_unit))
                self.domains[f_unit.id] = new_domain
                
        return True, pruned_history

    def _solve(self, units: List[SessionOccurrence], state: GlobalState, depth: int) -> Tuple[bool, List[SessionOccurrence], str]:
        if time.time() - self.start_time > self.max_generation_seconds:
            return False, [], "Generation timed out while searching for a feasible timetable."
            
        if depth > self.stats["max_depth"]:
            self.stats["max_depth"] = depth
            
        if depth >= len(units):
            return True, units, ""
            
        unit = units[depth]
        candidates = list(self.domains[unit.id])
        
        if not candidates:
            msg = f"Failed at {unit.subject_name}. Teacher: {unit.teacher_id}. No valid slots left."
            return False, [], msg
            
        scored_candidates = []
        for day, idx in candidates:
            score = self._evaluate_candidate(unit, state, day, idx, units[:depth])
            scored_candidates.append((score, day, idx))
            
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        for score, day, idx in scored_candidates:
            state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            time_slot_obj = next((ts for ts in self.time_slots if ts.idx == idx), None)
            unit.assigned_slot = TimeSlot(day=day, idx=idx, start_time=time_slot_obj.start_time, end_time=self.time_slots[idx + unit.duration - 1].end_time)
            
            fc_ok, pruned_history = self._forward_check_prune(unit, state)
            
            if fc_ok:
                success, result_units, msg = self._solve(units, state, depth + 1)
                if success:
                    return True, result_units, ""
                
            self.stats["backtracks"] += 1
                    
            # Backtrack state and domains
            for p_u_id, p_slots in pruned_history:
                self.domains[p_u_id].extend(p_slots)
                
            unit.assigned_slot = None
            state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            
        self.stats["backjumps"] += 1
        msg = f"Backtracking exhausted for {unit.subject_name}. All {len(candidates)} candidates led to future failures."
        return False, [], msg
        
    def _calculate_global_gap_score(self, state: GlobalState) -> int:
        total_penalty = 0
        for c_id, days_data in state.class_busy.items():
            for day, slots in days_data.items():
                if not slots: continue
                indices = sorted(list(slots))
                total_penalty += (indices[-1] - indices[0] + 1 - len(indices)) * 100
                
        for t_id, days_data in state.teacher_busy.items():
            for day, slots in days_data.items():
                if not slots: continue
                indices = sorted(list(slots))
                total_penalty += (indices[-1] - indices[0] + 1 - len(indices)) * 50
        return total_penalty
        
    def _calculate_local_gap_score(self, teacher_id: str, target_classes: List[str], state: GlobalState) -> int:
        penalty = 0
        if teacher_id and teacher_id in state.teacher_busy:
            for day, slots in state.teacher_busy[teacher_id].items():
                if not slots: continue
                indices = sorted(list(slots))
                penalty += (indices[-1] - indices[0] + 1 - len(indices)) * 50
                
        for c_id in target_classes:
            if c_id in state.class_busy:
                for day, slots in state.class_busy[c_id].items():
                    if not slots: continue
                    indices = sorted(list(slots))
                    penalty += (indices[-1] - indices[0] + 1 - len(indices)) * 100
                    
        return penalty

    def _optimize(self, units: List[SessionOccurrence], state: GlobalState):
        opt_start = time.time()
        
        current_penalty = self._calculate_global_gap_score(state)
        made_changes = True
        passes = 0
        
        while made_changes and passes < self.max_optimization_iterations:
            if time.time() - opt_start > self.max_optimization_seconds:
                break
                
            made_changes = False
            passes += 1
            
            for unit in units:
                if not unit.assigned_slot: continue
                
                if time.time() - opt_start > self.max_optimization_seconds:
                    break
                    
                self.stats["optimization_attempts"] += 1
                
                original_day = unit.assigned_slot.day
                original_idx = unit.assigned_slot.idx
                
                old_local = self._calculate_local_gap_score(unit.teacher_id, unit.target_classes, state)
                
                state.unassign(unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration)
                
                candidates = self._get_valid_candidates(unit, state)
                
                best_delta = 0
                best_move = None
                
                for day, idx in candidates:
                    if day == original_day and idx == original_idx: continue
                    
                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    new_local = self._calculate_local_gap_score(unit.teacher_id, unit.target_classes, state)
                    delta = new_local - old_local
                    
                    if delta < best_delta:
                        best_delta = delta
                        best_move = (day, idx)
                        
                    state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                
                if best_move and best_delta < 0:
                    day, idx = best_move
                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    time_slot_obj = next((ts for ts in self.time_slots if ts.idx == idx), None)
                    unit.assigned_slot = TimeSlot(day=day, idx=idx, start_time=time_slot_obj.start_time, end_time=self.time_slots[idx + unit.duration - 1].end_time)
                    
                    current_penalty += best_delta
                    made_changes = True
                    self.stats["optimization_accepted"] += 1
                else:
                    state.assign(unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration)

    def _validate_timetable(self, units: List[SessionOccurrence], state: GlobalState) -> Tuple[bool, str]:
        for u in units:
            if not u.assigned_slot:
                return False, f"Missing assignment for {u.subject_name}"
        return True, "Valid"

    def generate(self, units: List[SessionOccurrence], state: GlobalState) -> Tuple[bool, List[SessionOccurrence], str, dict]:
        t_start = time.time()
        self.start_time = t_start
        
        # Initialize domains and dependencies
        for u in units:
            self.domains[u.id] = self._get_valid_candidates(u, state)
            if u.teacher_id:
                self.teacher_deps[u.teacher_id].append(u)
            for c_id in u.target_classes:
                self.class_deps[c_id].append(u)
                
        # Feasibility phase
        t_feas = time.time()
        success, sched, msg = self._solve(units, state, 0)
        self.stats["feasibility_time"] = time.time() - t_feas
        
        if not success:
            self.stats["total_time"] = time.time() - t_start
            return False, sched, msg, self.stats
            
        # Optimization phase
        t_opt = time.time()
        self._optimize(sched, state)
        self.stats["optimization_time"] = time.time() - t_opt
        
        # Validation phase
        t_val = time.time()
        v_ok, v_msg = self._validate_timetable(sched, state)
        self.stats["validation_time"] = time.time() - t_val
        
        self.stats["total_time"] = time.time() - t_start
        
        if not v_ok:
            return False, sched, f"Validation failed: {v_msg}", self.stats
            
        return True, sched, "Generation successful.", self.stats
