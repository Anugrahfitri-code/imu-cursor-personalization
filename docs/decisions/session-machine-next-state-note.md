# Note: `SessionMachine.next_state()` is defective — deliberately left unfixed

**Status:** Known bug, intentionally NOT fixed in the session-runner commit.
**Component:** `pc/experiment/session/state_machine.py` → `SessionMachine.next_state()`
**Filed during:** Stage 30 experiment session runner implementation.

---

## 1. The bug

`next_state()` is documented as *"Return the next scheduled state without applying it."*
It is meant to answer **"given this session's `condition_order`, what runs next?"**
It does not. For every non-`PAUSE` state it is equivalent to:

```python
return TRANSITIONS[self.state][0]
```

i.e. it ignores `condition_order` completely.

### Root cause — one missing `continue`

```python
for candidate in TRANSITIONS.get(self.state, ()):
    if candidate in CONDITION_STATES:
        code = candidate.split("_")[-1]
        if code in self.condition_order:      # <-- guard
            return candidate
    return candidate                          # <-- unconditional, same indent
```

Two independent defects in the same three lines:

1. **The unconditional `return candidate` is at the same indentation level as the
   `if` guard**, not nested inside it. The `for` loop therefore always returns on
   its **first** candidate and can never advance to the second one. The
   "find the first candidate still in the session order" loop is dead code.
2. **The guard is a membership test against the full `condition_order`**, not a
   "has not run yet" test. Even if it were reached, it does not exclude
   conditions already completed earlier in the session.

Net effect: the guard can suppress a return but can never *influence which*
candidate is chosen.

### Reproduction

`validate_order_reachable` constrains `condition_order` to be a subsequence of the
frozen `P0 -> P2C -> L0 -> L2C` chain, so the valid order `["P0", "L2C"]`
(skip P2C and L0) is enough:

```python
m = SessionMachine(session_id="s", participant_id="p",
                   condition_order=["P0", "L2C"])
m.state = "CONDITION_P0"
m.next_state()      # -> "CONDITION_P2C"
```

`CONDITION_P2C` **is not in this session's condition order at all**. The correct
answer is `CONDITION_L2C`. If this value were used to drive the session, the
runner would execute a condition that was explicitly skipped, and the manifest
would misreport the design.

### Scope, measured

Exhaustively over all 15 valid `condition_order` subsequences x all
non-terminal states:

| Metric | Value |
| --- | --- |
| Cases examined | 120 |
| Cases returning the wrong successor | **88** |
| Cases returning a condition *not in the session order* | **88** |

The 32 correct answers are exactly those where the canonical first successor
happens to be the session's next condition.

### Why it was never caught

`next_state()` has **exactly one test** in the whole repository
(`test_stage29_session_machine.py:113`):

```python
machine.transition("PAUSE")
assert machine.next_state() == "INITIALIZATION"
```

That assertion exercises the `if self.state == "PAUSE": return self._pause_return`
early return — the one branch that is actually correct. The buggy loop below it
has **zero** test coverage.

---

## 2. Why it has not been fixed yet

The Stage 30 state machine is under an explicit **frozen contract**. Its
transition table, ordering rules and state names are treated as a fixed,
already-reviewed specification; changing `next_state()` would alter observable
behaviour of a component that other work and documentation assume to be stable.

Fixing it properly is also **not a mechanical change**. A correct
implementation must answer "which conditions are still *pending*?", and
`SessionMachine` does not track which conditions have already run — it stores
only the current `state`. Answering that question correctly requires a new piece
of state (a progress marker or run-ledger), which changes the dataclass's
fields, its constructor, and every call site.

Deciding *which* of those designs is correct is a specification decision, not a
bugfix, and it belongs to the state-machine owner rather than to a session-runner
change. Bundling it here would silently expand the blast radius of this commit.

---
## 3. The session runner does not depend on `next_state()`

`SessionRunner` (`pc/experiment/session/runner.py`) never calls `next_state()`.
It drives the machine exclusively through the **checked** API:

- `machine.transition(state)` — validates against the frozen table and refuses
  anything not explicitly permitted
- `machine.advance_to(state)` — re-checks the hard time cap before applying
- `machine.stop_session(reason)`

The runner computes its own ordered plan and passes each target state explicitly:

```python
target = self._planned_states()[index]
machine.transition(target)
```

Consequences:

- The Stage 30 happy path, fault path and time-cap path are all exercised and
  covered by tests **without** `next_state()` participating at all.
- **The runner is not affected by this bug.** Provenance in the manifest is
  correct, because the manifest is built from the runner's own plan, not from
  `next_state()`.
- Fixing `next_state()` later will therefore **not** change runner behaviour —
  only the convenience helper's output.

---

## 4. Risk of changing it now

| Risk | Severity | Detail |
| --- | --- | --- |
| Wrong "fix" breaks counterbalancing | High | The naive fix — adding the missing `continue` and dedenting the `return` — still uses the *full* `condition_order` as the membership set, so it would happily return a condition that already ran. It fixes one bug and leaves the other. |
| Requires new instance state | High | Tracking "already run" needs a progress marker/ledger on `SessionMachine`, changing the frozen dataclass and all call sites. |
| Frozen-contract churn | Medium | Any behaviour change ripples into specs, docs and Stage 29/30 test expectations. |
| Test surface is too small | Medium | With one assertion, the suite cannot distinguish a correct fix from a regression. Property-based tests over `condition_order` x state must be written **first**. |
| Silent scope creep | Medium | A state-machine semantics change smuggled into a session-runner commit makes bisect and review misleading. |

### Recommended follow-up (separate, sequenced change)

1. Write property-based tests encoding the real contract: *the returned state
   is always the first still-pending successor under `condition_order`*, across
   all valid subsequences. These must fail on today's code.
2. Decide and document the tracking design (run-ledger vs. derived-from-state).
3. Implement, then confirm Stage 29 and Stage 30 suites are unaffected.

Until then, treat `next_state()` as **unreliable** and use explicit
`transition()` calls, as the session runner does.
