"""LLM proposals -> verified catalog values -> deterministic state transaction.

The model never mutates state and never creates exact-match evidence by assertion.  It proposes typed
operations; this module validates them, resolves values against the real catalog vocabulary, and
applies the accepted operations atomically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.understand.attributes import normalise
from src.state.session import (
    AmbiguousConstraint,
    Constraint,
    ConstraintAlternative,
    SessionState,
)


ALLOWED_ATTRIBUTES = frozenset(
    {"material", "color", "size", "style", "brand", "budget", "feature", "use_case"}
)
ALLOWED_OPERATIONS = frozenset({"add", "remove", "replace", "confirm", "no_preference"})
ALLOWED_POLARITIES = frozenset({"require", "avoid"})
ALLOWED_STRENGTHS = frozenset({"hard", "soft"})
ALLOWED_KINDS = frozenset(
    {"buying", "browsing", "override_open", "reply", "override", "no_preference", "null_ask", "unknown"}
)
MIN_CONFIDENCE = 0.55


def _clean(value: object, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" .;,\t\n")[:limit]


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9%$]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class IntentOperation:
    op: str
    attribute: str
    value: str
    evidence: str
    polarity: str = "require"
    strength: str = "hard"
    confidence: float = 1.0
    group: str = ""


@dataclass(frozen=True)
class CanonicalResolution:
    canonical: str | None = None
    value: str | None = None
    alternatives: tuple[ConstraintAlternative, ...] = ()


@dataclass(frozen=True)
class RoutingDecision:
    """One model call supplies both routing and any hybrid interpretation."""

    route: str
    normalized_text: str
    kind: str
    category: str
    attribute: str
    operations: tuple[IntentOperation, ...]


def validate_operations(rows: object, message: str) -> list[IntentOperation]:
    """Convert untrusted model JSON into a narrow, typed proposal list."""
    if not isinstance(rows, list):
        return []
    accepted: list[IntentOperation] = []
    for row in rows[:8]:
        if not isinstance(row, dict):
            continue
        op = _clean(row.get("op")).lower()
        attribute = _clean(row.get("attribute")).lower()
        value = _clean(row.get("value"))
        evidence = _clean(row.get("evidence")) or _clean(message)
        polarity = _clean(row.get("polarity") or "require").lower()
        strength = _clean(row.get("strength") or "hard").lower()
        group = _clean(row.get("group"), 40).lower()
        try:
            confidence = float(row.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue
        if op not in ALLOWED_OPERATIONS or attribute not in ALLOWED_ATTRIBUTES:
            continue
        if op not in {"no_preference", "confirm"} and not value:
            continue
        if polarity not in ALLOWED_POLARITIES or strength not in ALLOWED_STRENGTHS:
            continue
        if not 0.0 <= confidence <= 1.0:
            continue
        if confidence < MIN_CONFIDENCE and (not group or confidence < 0.01):
            continue
        if evidence.lower() not in message.lower():
            continue
        accepted.append(
            IntentOperation(op, attribute, value, evidence, polarity, strength, confidence, group)
        )
    grouped: dict[str, list[IntentOperation]] = {}
    for operation in accepted:
        if operation.group:
            grouped.setdefault(operation.group, []).append(operation)
    return [
        operation
        for operation in accepted
        if operation.confidence >= MIN_CONFIDENCE
        or (
            operation.group
            and len(grouped.get(operation.group, ())) > 1
            and max(item.confidence for item in grouped[operation.group]) >= MIN_CONFIDENCE
        )
    ]


def state_for_prompt(state: SessionState) -> dict:
    return {
        "turn": state.turn,
        "category": state.category,
        "category_surface": state.category_surface,
        "category_hypotheses": state.category_hypotheses[:8],
        "recent_messages": state.history[-4:],
        "active": [
            {
                "attribute": item.attribute,
                "value": item.value,
                "polarity": item.polarity,
                "strength": item.strength,
                "turn": item.turn,
            }
            for item in state.live()
        ],
        "ambiguous": [
            {
                "evidence": item.evidence,
                "alternatives": [
                    {"attribute": alt.attribute, "value": alt.value, "confidence": alt.confidence}
                    for alt in item.alternatives
                ],
            }
            for item in state.live_ambiguities()
        ],
    }


class IntentPipeline:
    """Restore unknown wording to verified fixed-template state."""

    def __init__(self, index, llm, category_belief=None) -> None:
        self.index = index
        self.llm = llm
        self.category_belief = category_belief

    def interpret(self, message: str, state: SessionState) -> list[IntentOperation]:
        rows = self.llm.interpret_operations(message, state_for_prompt(state)) or []
        return validate_operations(rows, message)

    def decide(self, message: str, state: SessionState) -> RoutingDecision:
        if hasattr(self.llm, "restore_template"):
            payload = self.llm.restore_template(message, state_for_prompt(state)) or {}
            rows = payload.get("operations") or []
            route = _clean(payload.get("route")).lower()
            normalized = _clean(payload.get("normalized_text"), 1500)
            kind = _clean(payload.get("kind")).lower()
            category = _clean(payload.get("category"))
            attribute = _clean(payload.get("attribute")).lower()
        else:
            rows = self.llm.interpret_operations(message, state_for_prompt(state)) or []
            route, normalized, kind, category, attribute = "hybrid", message, "unknown", "", ""
        if kind not in ALLOWED_KINDS:
            kind = "unknown"
        if category and category.lower() not in message.lower():
            category = ""
        if attribute not in ALLOWED_ATTRIBUTES:
            attribute = ""
        operations = validate_operations(rows, message)
        # Old cache entries and test doubles predate the route field. Treat a meaningful
        # interpretation as hybrid, and an empty/failed response as deterministic fallback.
        if route not in {"deterministic", "hybrid"}:
            route = "hybrid" if kind != "unknown" or operations else "deterministic"
        if not normalized:
            normalized = message
        return RoutingDecision(
            route, normalized, kind, category, attribute, tuple(operations)
        )

    def _candidate_records(self, operation: IntentOperation, state: SessionState) -> list[dict]:
        if hasattr(self.index, "canonical_candidate_records"):
            rows = self.index.canonical_candidate_records(
                operation.attribute, operation.value, limit=8
            )
        else:
            rows = [
                {"label": label, "attribute": operation.attribute,
                 "value": self._normalised_value(operation.attribute, label), "score": 1.0,
                 "support": 1}
                for label in self.index.canonical_candidates(
                    operation.attribute, operation.value, limit=8
                )
            ]
        if state.category_surface and self.category_belief is not None and hasattr(
            self.index, "concept_support"
        ):
            pool = self.category_belief.pool(state.category_surface)
            for row in rows:
                row["joint_support"] = self.index.concept_support(
                    str(row["attribute"]), str(row["value"]), pool
                )
            rows.sort(key=lambda row: (
                -int(row.get("joint_support") or 0),
                -float(row.get("score") or 0.0),
                -int(row.get("support") or 0),
            ))
        return rows

    @staticmethod
    def _alternatives(records: list[dict], operation: IntentOperation) -> tuple[ConstraintAlternative, ...]:
        rows = records[:4]
        if not rows:
            return ()
        raw = [
            max(0.01, float(row.get("score") or 0.0))
            * (1.0 + min(4.0, float(row.get("joint_support") or 0.0) ** 0.25))
            for row in rows
        ]
        total = sum(raw)
        return tuple(
            ConstraintAlternative(
                text=str(row["label"]),
                attribute=str(row["attribute"]),
                value=str(row["value"]),
                confidence=operation.confidence * weight / total,
            )
            for row, weight in zip(rows, raw)
        )

    def _canonical(self, operation: IntentOperation, state: SessionState) -> CanonicalResolution:
        exact = self.index.exact_canonical(operation.attribute, operation.value)
        expanded = _key(operation.value) not in _key(operation.evidence)
        trusted_alias = bool(
            hasattr(self.index, "is_trusted_alias")
            and self.index.is_trusted_alias(
                operation.attribute, operation.evidence, operation.value
            )
        )
        if exact and (not expanded or trusted_alias):
            return CanonicalResolution(
                canonical=exact,
                value=self._normalised_value(operation.attribute, exact),
            )
        if exact and expanded:
            # The model may expand one ambiguous surface span into several grouped meanings. Each
            # meaning gets one catalog-supported hypothesis; it must not explode into many raw label
            # variants or crowd the other meanings out of the probability mixture.
            return CanonicalResolution(alternatives=(ConstraintAlternative(
                text=exact,
                attribute=operation.attribute,
                value=self._normalised_value(operation.attribute, operation.value),
                confidence=operation.confidence,
            ),))

        records = self._candidate_records(operation, state)
        if expanded and operation.group and records:
            return CanonicalResolution(alternatives=(ConstraintAlternative(
                text=str(records[0]["label"]),
                attribute=operation.attribute,
                value=self._normalised_value(operation.attribute, operation.value),
                confidence=operation.confidence,
            ),))
        phrase_key = _key(operation.evidence if expanded else operation.value)
        # A short non-literal prefix is an abbreviation, not exact evidence. Preserve its candidate
        # meanings even when one is much more common; context may resolve it on a later turn.
        if expanded and not trusted_alias:
            return CanonicalResolution(alternatives=self._alternatives(records, operation))
        if len(phrase_key) <= 4:
            return CanonicalResolution(alternatives=self._alternatives(records, operation))
        # The interpreter has already used conversation semantics. Catalog resolution is now wholly
        # deterministic: a clear concept-level winner commits; everything else remains a mixture.
        if records and operation.confidence >= 0.75:
            top = records[0]
            runner_up = float(records[1]["score"]) if len(records) > 1 else 0.0
            if float(top["score"]) >= 3.0 and float(top["score"]) - runner_up >= 0.5:
                return CanonicalResolution(
                    canonical=str(top["label"]),
                    value=str(top["value"]),
                )
        return CanonicalResolution(alternatives=self._alternatives(records, operation))

    @staticmethod
    def _normalised_value(attribute: str, text: str) -> str:
        for found_attribute, value in normalise(text):
            if found_attribute == attribute:
                return value
        return _key(text)[:60]

    @staticmethod
    def _matches(constraint: Constraint, operation: IntentOperation) -> bool:
        if not constraint.alive or constraint.attribute != operation.attribute:
            return False
        wanted = _key(operation.value)
        normalized = IntentPipeline._normalised_value(operation.attribute, operation.value)
        return wanted in {
            _key(constraint.value), _key(constraint.text), _key(constraint.source_text or "")
        } or normalized == constraint.value

    def apply(
        self,
        state: SessionState,
        operations: list[IntentOperation],
        *,
        erase: str = "demote",
    ) -> int:
        """Validate the full proposal first, then apply it as one deterministic transaction."""
        prepared: list[tuple[IntentOperation, CanonicalResolution]] = []
        for operation in operations:
            resolution = CanonicalResolution()
            if operation.op in {"add", "replace", "confirm"} and operation.value:
                resolution = self._canonical(operation, state)
            prepared.append((operation, resolution))

        # Alternative operations sharing one explicit group describe one uncertain evidence span.
        # Store one probability mixture and skip every state mutation in that group.
        grouped: dict[str, list[tuple[IntentOperation, CanonicalResolution]]] = {}
        for operation, resolution in prepared:
            if operation.group:
                grouped.setdefault(operation.group, []).append((operation, resolution))
        ambiguous_groups = {name for name, rows in grouped.items() if len(rows) > 1}
        for name in ambiguous_groups:
            rows = grouped[name]
            alternatives: list[ConstraintAlternative] = []
            for operation, resolution in rows:
                if resolution.canonical and resolution.value:
                    alternatives.append(ConstraintAlternative(
                        resolution.canonical, operation.attribute, resolution.value,
                        operation.confidence,
                    ))
                alternatives.extend(resolution.alternatives)
            total = sum(item.confidence for item in alternatives) or 1.0
            state.add_ambiguity(AmbiguousConstraint(
                evidence=rows[0][0].evidence,
                alternatives=tuple(
                    ConstraintAlternative(a.text, a.attribute, a.value, a.confidence / total)
                    for a in alternatives[:6]
                ),
                turn=state.turn,
                polarity=rows[0][0].polarity,
            ))

        changed = 0
        for operation, resolution in prepared:
            if operation.group in ambiguous_groups:
                continue
            canonical = resolution.canonical
            if operation.op == "no_preference":
                state.asked[operation.attribute] = False
                continue
            if operation.op == "confirm":
                for item in state.live():
                    if self._matches(item, operation):
                        item.confidence = max(item.confidence, operation.confidence)
                        if canonical and resolution.value:
                            item.source_text = operation.evidence
                            item.text = canonical
                            item.value = resolution.value
                            item.tier = "llm-canonical"
                        elif "llm-confirmed" not in item.tier:
                            item.tier += "+llm-confirmed"
                continue
            if operation.op == "remove":
                matched = [item for item in state.live() if self._matches(item, operation)]
                for item in matched:
                    state.retire(item, turn=state.turn, demote=erase == "demote")
                    changed += 1
                if matched:
                    state.override_seen = True
                    state.route = "override"
                changed += state.resolve_ambiguities(operation.attribute)
                continue
            # A model-proposed value is never ranking evidence until it resolves to a real catalog
            # label.  In particular, do not erase old state for an unverified replacement.
            if canonical is None:
                if resolution.alternatives and operation.op in {"add", "replace"}:
                    state.add_ambiguity(AmbiguousConstraint(
                        evidence=operation.evidence,
                        alternatives=resolution.alternatives,
                        turn=state.turn,
                        polarity=operation.polarity,
                    ))
                continue
            if operation.op == "replace":
                changed += state.resolve_ambiguities(operation.attribute)
                for item in [
                    c for c in state.live()
                    if c.attribute == operation.attribute and c.turn < state.turn
                ]:
                    state.retire(item, turn=state.turn, demote=erase == "demote")
                    changed += 1
                state.override_seen = True
                state.route = "override"

            text = canonical
            value = resolution.value or self._normalised_value(operation.attribute, canonical)
            before = len(state.constraints)
            state.add(
                Constraint(
                    text=text,
                    attribute=operation.attribute,
                    value=value,
                    turn=state.turn,
                    tier="llm-canonical",
                    source_text=operation.evidence,
                    polarity=operation.polarity,
                    strength=operation.strength,
                    confidence=operation.confidence,
                )
            )
            changed += int(len(state.constraints) > before)
        state.rebuild_slots()
        return changed

    @staticmethod
    def _render(kind: str, category: str, attribute: str, state: SessionState) -> str | None:
        current = list(dict.fromkeys(
            item.text for item in state.live() if item.turn == state.turn and item.polarity == "require"
        ))
        blob = "; ".join(current)
        if kind == "buying" and category and blob:
            return f"I'm looking for {category}. A key requirement is: {current[0]}."
        if kind == "browsing" and category:
            return f"I'm looking for {category}, but I'm still exploring."
        if kind == "override_open" and category and blob:
            return f"I'm looking for {category}. {blob}"
        if kind == "reply" and blob:
            return f"For that, what matters is: {blob}."
        if kind == "override" and blob:
            return f"Actually, ignore my earlier preference. What I need is: {blob}."
        if kind == "no_preference" and attribute:
            return f"I don't have an additional preference for {attribute}."
        if kind == "null_ask":
            return "Those options are not quite right yet. Ask me about one specific attribute."
        return None

    def process_decision(
        self,
        message: str,
        state: SessionState,
        decision: RoutingDecision,
        *,
        erase: str = "demote",
    ) -> int:
        kind = decision.kind
        category_phrase = decision.category
        attribute = decision.attribute
        changed = self.apply(state, list(decision.operations), erase=erase)

        category = ""
        if category_phrase and self.category_belief is not None:
            if hasattr(self.category_belief, "resolve_candidates"):
                hypotheses = self.category_belief.resolve_candidates(category_phrase)
                if hypotheses:
                    state.category_surface = category_phrase
                    state.category_hypotheses = hypotheses
            category = self.category_belief.resolve_phrase(category_phrase) or ""
            if category and not state.category_hypotheses:
                state.category_hypotheses = [(category, 1.0)]
            if category:
                state.category = category
        if kind == "buying":
            state.route = "buying"
        elif kind == "browsing":
            state.route = "browsing"
        elif kind in {"override", "override_open"}:
            state.route = "override"
        if kind == "override":
            state.override_seen = True
            for item in state.constraints:
                if item.turn <= 1 and item.superseded_turn is None:
                    state.retire(item, turn=state.turn, demote=erase == "demote")

        restored = self._render(kind, category, attribute, state)
        if restored:
            state.restored_messages[state.turn] = restored
            # ⚠️ DELIBERATE DEVIATION from the source branch, which incremented `template_hits` here.
            # That flips `paraphrased()` to False and moves the session into the patient branch of
            # the depth policy on the strength of a model claim. See SessionState.paraphrased().
            state.restored_hits += 1
        if kind != "unknown":
            state.llm_restoration_hits += 1
        return changed

    def process(self, message: str, state: SessionState, *, erase: str = "demote") -> int:
        """Compatibility entry point: decide and apply using one model call."""
        decision = self.decide(message, state)
        state.normalized_messages[state.turn] = decision.normalized_text
        state.router_routes[state.turn] = decision.route
        return self.process_decision(message, state, decision, erase=erase)
