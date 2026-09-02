import time
from typing import List, Tuple
import collections

from utils.scheduler.core import TimeSlot, SessionOccurrence, GlobalState
from utils.scheduler.diagnostics import GenerationDiagnostics, ReasonCodes


class TimetableEngine:
    def __init__(self, time_slots: List[TimeSlot], days: List[str], max_iterations=1000, seed=None):
        self.time_slots = time_slots
        self.time_slots_by_index = {slot.idx: slot for slot in time_slots}
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
            "total_time": 0.0,
        }
        self.domains = {}
        self.teacher_deps = collections.defaultdict(list)
        self.class_deps = collections.defaultdict(list)
        self.failure_counts = collections.defaultdict(int)
        self.deepest_failure_unit = None

        self.max_generation_seconds = 3.0
        self.max_optimization_seconds = 1.0
        self.max_optimization_iterations = 2

        self.start_time = 0.0

    def _get_valid_candidates(
        self, unit: SessionOccurrence, state: GlobalState
    ) -> List[Tuple[str, int]]:
        candidates = []
        for day in self.days:
            if unit.preferred_days and day not in unit.preferred_days:
                continue

            if unit.teacher_id and unit.teacher_id in state.teacher_available_days:
                if day not in state.teacher_available_days[unit.teacher_id]:
                    continue

            max_start_idx = len(self.time_slots) - unit.duration
            for idx in range(max_start_idx + 1):
                if state.is_free(unit.teacher_id, unit.target_classes, day, idx, unit.duration):
                    candidates.append((day, idx))
        return candidates

    def _evaluate_candidate(
        self,
        unit: SessionOccurrence,
        state: GlobalState,
        day: str,
        idx: int,
        scheduled_units: List[SessionOccurrence],
    ) -> int:
        self.stats["candidates_evaluated"] += 1
        score = 0

        def class_has_class(c_id, d, i):
            return i in state.class_busy.get(c_id, {}).get(d, set())

        def teacher_has_class(t_id, d, i):
            if not t_id:
                return False
            return i in state.teacher_busy.get(t_id, {}).get(d, set())

        for c_id in unit.target_classes:
            adj_before = class_has_class(c_id, day, idx - 1) if idx > 0 else False
            adj_after = (
                class_has_class(c_id, day, idx + unit.duration)
                if idx + unit.duration < len(self.time_slots)
                else False
            )

            if adj_before or adj_after:
                score += 50
            else:
                score -= 30

        if unit.teacher_id:
            adj_before_t = teacher_has_class(unit.teacher_id, day, idx - 1) if idx > 0 else False
            adj_after_t = (
                teacher_has_class(unit.teacher_id, day, idx + unit.duration)
                if idx + unit.duration < len(self.time_slots)
                else False
            )

            if adj_before_t or adj_after_t:
                score += 30
            else:
                score -= 20

        # Subject distribution penalty
        same_day_count = 0
        for s_unit in scheduled_units:
            if (
                s_unit.subject_id == unit.subject_id
                and s_unit.assigned_slot
                and s_unit.assigned_slot.day == day
            ):
                same_day_count += 1

        if same_day_count > 0:
            score -= 200

        return score

    def _forward_check_prune(self, assigned_unit: SessionOccurrence, state: GlobalState):
        self.stats["forward_check_calls"] += 1
        pruned_history = []
        affected_units = {}

        if assigned_unit.teacher_id:
            for f_u in self.teacher_deps[assigned_unit.teacher_id]:
                affected_units[f_u.id] = f_u
        for c_id in assigned_unit.target_classes:
            for f_u in self.class_deps[c_id]:
                affected_units[f_u.id] = f_u

        for f_unit in affected_units.values():
            if f_unit.assigned_slot is not None:
                continue

            new_domain = []
            pruned_for_this_unit = []

            for c_day, c_idx in self.domains[f_unit.id]:
                if not state.is_free(
                    f_unit.teacher_id, f_unit.target_classes, c_day, c_idx, f_unit.duration
                ):
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

    def _presolve(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> "GenerationDiagnostics":
        teacher_req = collections.defaultdict(int)
        class_req = collections.defaultdict(int)

        for u in units:
            if u.teacher_id:
                teacher_req[u.teacher_id] += u.duration
            for c in u.target_classes:
                class_req[c] += u.duration

        total_slots = len(self.time_slots) * len(self.days)

        for t_id, req in teacher_req.items():
            base_max = state.teacher_max_hours.get(t_id, total_slots)

            # Bound capacity by available days constraint
            if t_id in state.teacher_available_days:
                allowed_days = [d for d in self.days if d in state.teacher_available_days[t_id]]
                hard_max = len(allowed_days) * len(self.time_slots)
                max_h = min(base_max, hard_max)
            else:
                max_h = base_max
            if req > max_h:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_TEACHER_CAPACITY,
                    primary_bottleneck=f"Teacher: {t_id}",
                    affected_teachers=[t_id],
                    required_capacity=req,
                    available_capacity=max_h,
                    shortage=req - max_h,
                    suggestions=[
                        "Increase teacher maximum hours",
                        "Assign another teacher to some subjects",
                        "Reduce weekly requirement",
                    ],
                )

        for c_id, req in class_req.items():
            if req > total_slots:
                return GenerationDiagnostics(
                    status="FAILED",
                    reason_code=ReasonCodes.INSUFFICIENT_CLASS_CAPACITY,
                    primary_bottleneck="Class weekly load exceeds configured teaching capacity",
                    affected_courses=[c_id],
                    required_capacity=req,
                    available_capacity=total_slots,
                    shortage=req - total_slots,
                    suggestions=["Reduce total weekly hours for this class"],
                )

        return None

    def _solve(
        self, units: List[SessionOccurrence], state: GlobalState, depth: int
    ) -> Tuple[bool, List[SessionOccurrence], str]:
        if time.time() - self.start_time > self.max_generation_seconds:
            return False, [], "Generation timed out while searching for a feasible timetable."

        unassigned = [u for u in units if not u.assigned_slot]
        if not unassigned:
            return True, units, ""

        depth = len(units) - len(unassigned)
        if depth > self.stats["max_depth"]:
            self.stats["max_depth"] = depth

        min_domain = min(len(self.domains[u.id]) for u in unassigned)
        tied_domain = [u for u in unassigned if len(self.domains[u.id]) == min_domain]

        if not min_domain:
            # Short-circuit failure
            u = tied_domain[0]
            msg = f"Failed at {u.subject_name}. Teacher: {u.teacher_id}. No valid slots left."
            return False, [], msg

        if len(tied_domain) == 1:
            best_unit = tied_domain[0]
        else:
            # Apply scarcity tie-breaker
            def get_scarcity(u):
                s = 0
                if u.is_practical:
                    s += 50
                if len(u.target_classes) > 1:
                    s += 50
                return s

            scarcity_scores = [(get_scarcity(u), u) for u in tied_domain]
            max_scarcity = max(s[0] for s in scarcity_scores)
            tied_scarcity = [u for s, u in scarcity_scores if s == max_scarcity]

            if len(tied_scarcity) == 1:
                best_unit = tied_scarcity[0]
            else:
                # Regret tie-breaker ONLY for remaining tied units
                best_unit = None
                best_regret = -1
                for u in tied_scarcity:
                    domain = self.domains[u.id]
                    if len(domain) == 1:
                        regret = 9999
                    else:
                        scores = [
                            self._evaluate_candidate(u, state, d, i, units) for d, i in domain
                        ]
                        scores.sort(reverse=True)
                        regret = scores[0] - scores[1]

                    if regret > best_regret:
                        best_regret = regret
                        best_unit = u

        unit = best_unit
        candidates = list(self.domains[unit.id])

        if not candidates:
            self.failure_counts[unit.id] += 1
            msg = f"Failed at {unit.subject_name}. Teacher: {unit.teacher_id}. No valid slots left."
            return False, [], msg

        scored_candidates = []
        for day, idx in candidates:
            score = self._evaluate_candidate(unit, state, day, idx, units)
            scored_candidates.append((score, day, idx))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        for score, day, idx in scored_candidates:
            state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
            time_slot_obj = self.time_slots_by_index[idx]
            unit.assigned_slot = TimeSlot(
                day=day,
                idx=idx,
                start_time=time_slot_obj.start_time,
                end_time=self.time_slots[idx + unit.duration - 1].end_time,
            )

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

    def _calculate_class_balance(
        self, state: "GlobalState", target_classes: List[str] = None
    ) -> int:
        penalty = 0
        c_ids = target_classes if target_classes else list(state.class_busy.keys())
        for c_id in c_ids:
            days_data = state.class_busy.get(c_id, {})
            actual_counts = []
            for day in self.days:
                actual_counts.append(len(days_data.get(day, set())))

            total_periods = sum(actual_counts)
            if total_periods == 0:
                continue

            working_days_count = len(self.days)
            base_load = total_periods // working_days_count
            remainder = total_periods % working_days_count

            target_counts = [base_load + 1] * remainder + [base_load] * (
                working_days_count - remainder
            )

            actual_sorted = sorted(actual_counts, reverse=True)
            penalty += sum(abs(a - t) for a, t in zip(actual_sorted, target_counts))
        return penalty

    def _calculate_exact_gaps(self, state: GlobalState) -> tuple[int, int]:
        class_gaps = 0
        teacher_gaps = 0
        for c_id, days_data in state.class_busy.items():
            for day, slots in days_data.items():
                if not slots:
                    continue
                indices = sorted(list(slots))
                class_gaps += indices[-1] - indices[0] + 1 - len(indices)

        for t_id, days_data in state.teacher_busy.items():
            for day, slots in days_data.items():
                if not slots:
                    continue
                indices = sorted(list(slots))
                teacher_gaps += indices[-1] - indices[0] + 1 - len(indices)
        return class_gaps, teacher_gaps

    def _calculate_global_score(self, state: GlobalState) -> Tuple[int, int, int, int]:
        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        bal = self._calculate_class_balance(state)
        leading = self._calculate_leading_free_periods(state)
        return (c_gaps, bal, t_gaps, leading)

    def _calculate_local_score(
        self, teacher_id: str, target_classes: List[str], state: GlobalState
    ) -> Tuple[int, int, int, int]:
        c_gaps = 0
        t_gaps = 0
        if teacher_id and teacher_id in state.teacher_busy:
            for day, slots in state.teacher_busy[teacher_id].items():
                if not slots:
                    continue
                indices = sorted(list(slots))
                t_gaps += indices[-1] - indices[0] + 1 - len(indices)
        for c_id in target_classes:
            if c_id in state.class_busy:
                for day, slots in state.class_busy[c_id].items():
                    if not slots:
                        continue
                    indices = sorted(list(slots))
                    c_gaps += indices[-1] - indices[0] + 1 - len(indices)
        bal = self._calculate_class_balance(state, target_classes)
        leading = self._calculate_leading_free_periods(state, target_classes)
        return (c_gaps, bal, t_gaps, leading)

    def _calculate_leading_free_periods(
        self, state: GlobalState, target_classes: List[str] = None
    ) -> int:
        penalty = 0
        c_ids = target_classes if target_classes else list(state.class_busy.keys())
        for c_id in c_ids:
            if c_id in state.class_busy:
                for day, slots in state.class_busy[c_id].items():
                    if slots:
                        penalty += min(slots)
        return penalty

    def _optimize(self, units: List[SessionOccurrence], state: GlobalState):
        opt_start = time.time()

        made_changes = True
        passes = 0

        self.stats["optimization_attempts"] = 0
        self.stats["optimization_accepted"] = 0
        self.stats["swap_attempts"] = 0
        self.stats["swap_accepted"] = 0

        # Capture before optimization
        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        self.stats["class_internal_gaps_before"] = c_gaps
        self.stats["teacher_internal_gaps_before"] = t_gaps

        while made_changes and passes < self.max_optimization_iterations:
            if time.time() - opt_start > self.max_optimization_seconds:
                break

            made_changes = False
            passes += 1

            # --- 1. MOVE PHASE ---
            for unit in units:
                if not unit.assigned_slot:
                    continue

                if time.time() - opt_start > self.max_optimization_seconds:
                    break

                self.stats["optimization_attempts"] += 1

                original_day = unit.assigned_slot.day
                original_idx = unit.assigned_slot.idx

                old_local = self._calculate_local_score(unit.teacher_id, unit.target_classes, state)

                state.unassign(
                    unit.teacher_id, unit.target_classes, original_day, original_idx, unit.duration
                )

                candidates = self._get_valid_candidates(unit, state)

                best_score = old_local
                best_move = None

                for day, idx in candidates:
                    if day == original_day and idx == original_idx:
                        continue

                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    new_local = self._calculate_local_score(
                        unit.teacher_id, unit.target_classes, state
                    )
                    if new_local < old_local:
                        if best_move is None or new_local < best_score:
                            best_score = new_local
                            best_move = (day, idx)

                    state.unassign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)

                if best_move:
                    day, idx = best_move
                    state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                    time_slot_obj = self.time_slots_by_index[idx]
                    unit.assigned_slot = TimeSlot(
                        day=day,
                        idx=idx,
                        start_time=time_slot_obj.start_time,
                        end_time=self.time_slots[idx + unit.duration - 1].end_time,
                    )

                    made_changes = True
                    self.stats["optimization_accepted"] += 1
                else:
                    state.assign(
                        unit.teacher_id,
                        unit.target_classes,
                        original_day,
                        original_idx,
                        unit.duration,
                    )

            # Record state after MOVE
            if passes == 1:
                c_gaps_m, t_gaps_m = self._calculate_exact_gaps(state)
                self.stats["class_internal_gaps_after_move"] = c_gaps_m
                self.stats["teacher_internal_gaps_after_move"] = t_gaps_m

            # --- 2. SWAP PHASE (GAP DIRECTED) ---
            if not made_changes:
                gap_slots = []
                for c_id, days_data in state.class_busy.items():
                    for day, slots in days_data.items():
                        indices = sorted(list(slots))
                        if not indices:
                            continue
                        for i in range(indices[0], indices[-1] + 1):
                            if i not in indices:
                                gap_slots.append((c_id, day, i))

                for gap_class, gap_day, gap_idx in gap_slots:
                    if made_changes:
                        break
                    if time.time() - opt_start > self.max_optimization_seconds:
                        break

                    candidates_a = [
                        u
                        for u in units
                        if u.assigned_slot
                        and gap_class in u.target_classes
                        and u.duration == 1
                        and not (u.assigned_slot.day == gap_day and u.assigned_slot.idx == gap_idx)
                    ]

                    best_swap_score = None
                    best_swap = None

                    for unit_a in candidates_a:
                        day_a, idx_a = unit_a.assigned_slot.day, unit_a.assigned_slot.idx

                        candidates_b = [
                            u
                            for u in units
                            if u.assigned_slot
                            and u.assigned_slot.day == gap_day
                            and u.assigned_slot.idx == gap_idx
                            and u.duration == 1
                            and gap_class not in u.target_classes
                        ]

                        for unit_b in candidates_b:
                            if unit_a.id == unit_b.id:
                                continue

                            self.stats["swap_attempts"] += 1

                            day_b, idx_b = unit_b.assigned_slot.day, unit_b.assigned_slot.idx

                            if unit_a.preferred_days and day_b not in unit_a.preferred_days:
                                continue
                            if unit_b.preferred_days and day_a not in unit_b.preferred_days:
                                continue

                            def _score_subset():
                                c_gaps = 0
                                t_gaps = 0
                                affected_teachers = {unit_a.teacher_id, unit_b.teacher_id}
                                affected_classes = set(unit_a.target_classes).union(
                                    unit_b.target_classes
                                )

                                for t_id in affected_teachers:
                                    if not t_id:
                                        continue
                                    if t_id in state.teacher_busy:
                                        for d, slots in state.teacher_busy[t_id].items():
                                            if not slots:
                                                continue
                                            indices = sorted(list(slots))
                                            t_gaps += indices[-1] - indices[0] + 1 - len(indices)
                                for c_id in affected_classes:
                                    if c_id in state.class_busy:
                                        for d, slots in state.class_busy[c_id].items():
                                            if not slots:
                                                continue
                                            indices = sorted(list(slots))
                                            c_gaps += indices[-1] - indices[0] + 1 - len(indices)
                                bal = self._calculate_class_balance(state, list(affected_classes))
                                leading = self._calculate_leading_free_periods(
                                    state, list(affected_classes)
                                )
                                return (c_gaps, bal, t_gaps, leading)

                            old_subset_score = _score_subset()

                            state.unassign(
                                unit_a.teacher_id,
                                unit_a.target_classes,
                                day_a,
                                idx_a,
                                unit_a.duration,
                            )
                            state.unassign(
                                unit_b.teacher_id,
                                unit_b.target_classes,
                                day_b,
                                idx_b,
                                unit_b.duration,
                            )

                            valid = state.is_free(
                                unit_a.teacher_id,
                                unit_a.target_classes,
                                day_b,
                                idx_b,
                                unit_a.duration,
                            ) and state.is_free(
                                unit_b.teacher_id,
                                unit_b.target_classes,
                                day_a,
                                idx_a,
                                unit_b.duration,
                            )

                            if valid:
                                state.assign(
                                    unit_a.teacher_id,
                                    unit_a.target_classes,
                                    day_b,
                                    idx_b,
                                    unit_a.duration,
                                )
                                state.assign(
                                    unit_b.teacher_id,
                                    unit_b.target_classes,
                                    day_a,
                                    idx_a,
                                    unit_b.duration,
                                )

                                new_subset_score = _score_subset()
                                if new_subset_score < old_subset_score:
                                    if best_swap is None or new_subset_score < best_swap_score:
                                        best_swap_score = new_subset_score
                                        best_swap = (unit_a, unit_b, day_a, idx_a, day_b, idx_b)

                                state.unassign(
                                    unit_a.teacher_id,
                                    unit_a.target_classes,
                                    day_b,
                                    idx_b,
                                    unit_a.duration,
                                )
                                state.unassign(
                                    unit_b.teacher_id,
                                    unit_b.target_classes,
                                    day_a,
                                    idx_a,
                                    unit_b.duration,
                                )

                            # Always restore the original state for the next candidate
                            state.assign(
                                unit_a.teacher_id,
                                unit_a.target_classes,
                                day_a,
                                idx_a,
                                unit_a.duration,
                            )
                            state.assign(
                                unit_b.teacher_id,
                                unit_b.target_classes,
                                day_b,
                                idx_b,
                                unit_b.duration,
                            )

                    if best_swap:
                        unit_a, unit_b, day_a, idx_a, day_b, idx_b = best_swap

                        state.unassign(
                            unit_a.teacher_id, unit_a.target_classes, day_a, idx_a, unit_a.duration
                        )
                        state.unassign(
                            unit_b.teacher_id, unit_b.target_classes, day_b, idx_b, unit_b.duration
                        )

                        state.assign(
                            unit_a.teacher_id, unit_a.target_classes, day_b, idx_b, unit_a.duration
                        )
                        state.assign(
                            unit_b.teacher_id, unit_b.target_classes, day_a, idx_a, unit_b.duration
                        )

                        time_slot_b = self.time_slots_by_index[idx_b]
                        time_slot_a = self.time_slots_by_index[idx_a]

                        unit_a.assigned_slot = TimeSlot(
                            day=day_b,
                            idx=idx_b,
                            start_time=time_slot_b.start_time,
                            end_time=self.time_slots[idx_b + unit_a.duration - 1].end_time,
                        )
                        unit_b.assigned_slot = TimeSlot(
                            day=day_a,
                            idx=idx_a,
                            start_time=time_slot_a.start_time,
                            end_time=self.time_slots[idx_a + unit_b.duration - 1].end_time,
                        )

                        made_changes = True
                        self.stats["swap_accepted"] += 1

                        if made_changes:
                            break

            # --- 3. BALANCE REPAIR PHASE ---
            if not made_changes:
                b_opt_start = time.time()
                for unit in units:
                    if not unit.assigned_slot:
                        continue
                    if time.time() - b_opt_start > self.max_optimization_seconds:
                        break

                    # only care if the class is severely imbalanced
                    needs_balance = False
                    for c_id in unit.target_classes:
                        days_data = state.class_busy.get(c_id, {})
                        counts = [len(days_data.get(d, set())) for d in self.days]
                        if max(counts) - min(counts) > 1:
                            needs_balance = True
                            break
                    if not needs_balance:
                        continue

                    original_day = unit.assigned_slot.day
                    original_idx = unit.assigned_slot.idx

                    old_local = self._calculate_local_score(
                        unit.teacher_id, unit.target_classes, state
                    )

                    state.unassign(
                        unit.teacher_id,
                        unit.target_classes,
                        original_day,
                        original_idx,
                        unit.duration,
                    )
                    candidates = self._get_valid_candidates(unit, state)

                    best_score = old_local
                    best_move = None

                    for day, idx in candidates:
                        if day == original_day and idx == original_idx:
                            continue
                        state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                        new_local = self._calculate_local_score(
                            unit.teacher_id, unit.target_classes, state
                        )
                        if new_local < old_local:
                            if best_move is None or new_local < best_score:
                                best_score = new_local
                                best_move = (day, idx)
                        state.unassign(
                            unit.teacher_id, unit.target_classes, day, idx, unit.duration
                        )

                    if best_move:
                        day, idx = best_move
                        state.assign(unit.teacher_id, unit.target_classes, day, idx, unit.duration)
                        time_slot_obj = self.time_slots_by_index[idx]
                        unit.assigned_slot = TimeSlot(
                            day=day,
                            idx=idx,
                            start_time=time_slot_obj.start_time,
                            end_time=self.time_slots[idx + unit.duration - 1].end_time,
                        )
                        made_changes = True
                        self.stats["optimization_accepted"] += 1
                        break  # Start over since we made a change
                    else:
                        state.assign(
                            unit.teacher_id,
                            unit.target_classes,
                            original_day,
                            original_idx,
                            unit.duration,
                        )

    def _validate_timetable(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> Tuple[bool, str]:
        for u in units:
            if not u.assigned_slot:
                return False, f"Missing assignment for {u.subject_name}"
        return True, "Valid"

    def generate(
        self, units: List[SessionOccurrence], state: GlobalState
    ) -> Tuple[bool, List[SessionOccurrence], str, dict, "GenerationDiagnostics"]:
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
                    t_str = (
                        f"Prof. {hardest_unit.teacher_id}"
                        if hardest_unit.teacher_id
                        else "No Teacher"
                    )
                    additional_pressure = f"{hardest_unit.subject_name} ({t_str}) failed {self.failure_counts[hardest_unit_id]} times during deep search."

            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code=ReasonCodes.SEARCH_TIMEOUT
                if "timed out" in msg
                else ReasonCodes.NO_FEASIBLE_ASSIGNMENT,
                primary_bottleneck="Search tree exhausted or timed out. Complex constraints prevented a full schedule.",
                additional_pressure=additional_pressure,
                bottleneck_stats=dict(self.failure_counts),
                suggestions=[
                    "Loosen constraints",
                    "Increase teacher maximum hours",
                    "Check consecutive periods required",
                ],
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
        self.stats["total_sessions"] = len(units)

        c_gaps, t_gaps = self._calculate_exact_gaps(state)
        self.stats["class_internal_gaps"] = c_gaps
        self.stats["teacher_internal_gaps"] = t_gaps
        self.stats["gap_penalty"] = self._calculate_global_score(state)[0]  # legacy compatibility

        if not v_ok:
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code=ReasonCodes.NO_FEASIBLE_ASSIGNMENT,
                primary_bottleneck=f"Validation failed: {v_msg}",
            )
            return False, sched, f"Validation failed: {v_msg}", self.stats, diag

        diag = GenerationDiagnostics(
            status="SUCCESS", reason_code="SUCCESS", primary_bottleneck=None
        )
        return True, sched, "Timetable generated successfully.", self.stats, diag
