import time
import math
from typing import List, Tuple, Dict, Set
import collections

from utils.scheduler.core import TimeSlot, SessionOccurrence, GlobalState
from utils.scheduler.diagnostics import GenerationDiagnostics, ReasonCodes


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

    def _presolve(self, units: List[SessionOccurrence], state: GlobalState) -> 'GenerationDiagnostics':
        teacher_req = collections.defaultdict(int)
        class_req = collections.defaultdict(int)
        
        for u in units:
            if u.teacher_id:
                teacher_req[u.teacher_id] += u.duration
            for c in u.target_classes:
                class_req[c] += u.duration
                
        total_slots = len(self.time_slots) * len(self.days)
        
        for t_id, req in teacher_req.items():
            max_h = state.teacher_max_hours.get(t_id, total_slots)
            if req > max_h:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_TEACHER_CAPACITY,
                    primary_bottleneck=f"Teacher: {t_id}",
                    affected_teachers=[t_id],
                    required_capacity=req,
                    available_capacity=max_h,
                    shortage=req - max_h,
                    suggestions=["Increase teacher maximum hours", "Assign another teacher to some subjects", "Reduce weekly requirement"]
                )
                
        for c_id, req in class_req.items():
            if req > total_slots:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_CLASS_CAPACITY,
                    primary_bottleneck=f"Class: {c_id}",
                    affected_courses=[c_id],
                    required_capacity=req,
                    available_capacity=total_slots,
                    shortage=req - total_slots,
                    suggestions=["Reduce total weekly hours for this class"]
                )
                
        return None

    def _solve(self, units: List[SessionOccurrence], state: GlobalState, depth: int) -> Tuple[bool, List[SessionOccurrence], str]:
        if time.time() - self.start_time > self.max_generation_seconds:
            return False, [], "Generation timed out while searching for a feasible timetable."
            
        unassigned = [u for u in units if not u.assigned_slot]
        if not unassigned:
            return True, units, ""
            
        depth = len(units) - len(unassigned)
        if depth > self.stats["max_depth"]:
            self.stats["max_depth"] = depth
            
        best_unit = None
        best_score = None
        
        for u in unassigned:
            domain = self.domains[u.id]
            if not domain:
                msg = f"Failed at {u.subject_name}. Teacher: {u.teacher_id}. No valid slots left."
                return False, [], msg
                
            if len(domain) == 1:
                regret = 9999
            else:
                scores = [self._evaluate_candidate(u, state, d, i, units) for d, i in domain]
                scores.sort(reverse=True)
                regret = scores[0] - scores[1]
                
            scarcity = 0
            if u.is_practical: scarcity += 50
            if len(u.target_classes) > 1: scarcity += 50
            
            u_score = (len(domain), -regret, -scarcity)
            if best_score is None or u_score < best_score:
                best_score = u_score
                best_unit = u
                
        unit = best_unit
        candidates = list(self.domains[unit.id])
        
        if not candidates:
            self.failure_counts[unit.id] += 1
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
                if "timed out" in msg:
                    return False, [], msg
                
            self.stats["backtracks"] += 1
                    
            # Backtrack state and domains
            for p_u_id, p_slots in pruned_history:
                self.domains[p_u_id].extend(p_slots)
                
            unit.assigned_slot = None
            state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            
        self.stats["backjumps"] += 1
        self.failure_counts[unit.id] += 1
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

    def generate(self, units: List[SessionOccurrence], state: GlobalState) -> Tuple[bool, List[SessionOccurrence], str, dict, 'GenerationDiagnostics']:
        t_start = time.time()
        self.start_time = t_start
        
        # Presolve Phase
        diag = self._presolve(units, state)
        if diag:
            self.stats["total_time"] = time.time() - t_start
            return False, [], diag.reason_code, self.stats, diag

        
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
            
            additional_pressure = None
            if self.failure_counts:
                hardest_unit_id = max(self.failure_counts.items(), key=lambda x: x[1])[0]
                hardest_unit = next((u for u in units if u.id == hardest_unit_id), None)
                if hardest_unit:
                    t_str = f"Prof. {hardest_unit.teacher_id}" if hardest_unit.teacher_id else "No Teacher"
                    additional_pressure = f"{hardest_unit.subject_name} ({t_str}) failed {self.failure_counts[hardest_unit_id]} times during deep search."
                    
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code=ReasonCodes.SEARCH_TIMEOUT if "timed out" in msg else ReasonCodes.NO_FEASIBLE_ASSIGNMENT,
                primary_bottleneck="Search tree exhausted or timed out. Complex constraints prevented a full schedule.",
                additional_pressure=additional_pressure,
                bottleneck_stats=dict(self.failure_counts),
                suggestions=["Loosen constraints", "Increase teacher maximum hours", "Check consecutive periods required"]
            )
            return False, sched, msg, self.stats, diag
            
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
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code="VALIDATION_FAILED",
                primary_bottleneck=v_msg,
                suggestions=["Check internal scheduler logic"]
            )
            return False, sched, f"Validation failed: {v_msg}", self.stats, diag
            
        return True, sched, "Generation successful.", self.stats, None
