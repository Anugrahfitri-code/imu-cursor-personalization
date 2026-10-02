# L0 qualification notes

Scope: how the L0 supervised pipeline decides *what it trains on* and *what
counts as qualified*. These are policies, not code references.

## 1. User split policy

- Splits are by **`participant_id`** (the `COMMON_GRID_COLUMNS.participant_id`
  value). There is no `participant_code` column; the code field is the identity
  used for grouping, and label encoding happens after the split so that no
  integer encoding leaks across folds.
- `development_users` / `evaluation_users` are **explicit and mandatory**.
  An empty roster makes `load_l0_config()` fail closed rather than silently
  train on the whole cohort.
- No user may appear in both lists. The evaluation cohort is never touched
  before the qualification verdict is fixed; `evaluation_used` is recorded as
  `false` in the report to make that auditable.
- Windows never cross a participant or session boundary. Windowing is
  **causal and backward-anchored**, so the last `window` valid labels of a run
  are used as targets with their real preceding history rather than discarded.

## 2. Validation policy

- **Outer:** leave-one-user-out (LOUO) over the development cohort.
- **Inner:** grouped k-fold (`inner_folds`), grouped by user.
- The scaler is fitted on **inner training users only**
  (`scaler_fit_scope: inner_training_users`), so no held-out user contributes
  normalisation statistics.
- Held-out users are still windowed for feature construction; "held out" means
  excluded from scaler fitting and weight training, not from dataset assembly.
  Every fold's assignment is persisted in the report
  (`fold_assignments`) so the no-leak property is checkable after the fact.
- A held-out user is never present in its own inner training set, and inner
  train/validation users are disjoint by construction.

## 3. Padding policy

- Padding is **`REPEAT_FIRST`**, inherited from the frozen Stage 2.5 builder
  (`preprocessing/padding.py`). L0 does not define or override it.
- Padding supplies history only when a window reaches back before a run
  starts. It is a boundary-handling device for the first window of a run, not
  a general augmentation, and it never invents motion.
- History is confined to the current run: a gap in grid timestamps starts a new
  run instead of being windowed across.

## 4. Label alignment convention

**The pipeline implements `X[t-T+1 : t] -> Y(t-tau)`, not `Y(t)`.**
`tau` is **already compensated upstream**; L0 must not subtract it again.

- The frozen convention is
  `grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns`
  (`preprocessing/config.py`, `EXPECTED_LABEL_LAG_CONVENTION`).
- `preprocessing/labels.py` resolves `ref_vx_px_s` / `ref_vy_px_s` at
  `grid_label_pc_time_ns`, i.e. at `t - tau`. The label column therefore
  **already equals Y(t-tau)** by the time L0 sees a grid row.
- Verified empirically: with a strictly increasing reference ramp
  `v(t) = t` and `alignment_lag_ns = 5`, a row at `t = 8` resolves to
  `ref_vx_px_s = 3.0`, not `8.0`.
- Applying a lag in L0 as well would double-count `tau` and silently
  reintroduce exactly the clock/label misalignment Stage 2.5 removed.
- Windows are anchored at their own target index and never look forward, so
  no sample at time `> t - tau` can influence the prediction for it.

## 5. Qualification gate

All seven gates must pass for `status: QUALIFIED`; otherwise `NOT_QUALIFIED`.

| # | Gate key | Threshold | Condition |
|---|---|---|---|
| 1 | `active_motion_prediction` | `min_active_samples: 32` | At least 32 samples pass the active mask |
| 2 | `direction_agreement` | `min_direction_agreement: 0.55` | Mean angular agreement on active windows |
| 3 | `zero_velocity_baseline_comparison` | `zero_velocity_rmse_ratio_max: 0.95` | Pooled RMSE ratio vs predict-(0,0) |
| 4 | `per_user_consistency` | same ratio | **Every** held-out user individually beats the baseline |
| 5 | `closed_loop_sanity` | none | Predictions finite **and** max predicted speed > 0 |
| 6 | `inference_runtime` | `max_mean_latency_ms: 5.0` | Measured mean latency, after warmup |
| 7 | `artifact_reproducibility` | none | Same seed + config reproduces the checkpoint |

Notes on two gates that are easy to misread:

- Gate 4 is **per-user**, not averaged. A single user who fails to beat the
  baseline fails the whole verdict, so a strong cohort cannot mask one bad
  participant.
- Gate 5 is a **non-degeneracy** check, not an accuracy check. It only
  rejects an all-zero or non-finite output; passing it does not mean the
  model is any good.

Two distinct RMSE definitions are reported and must not be confused:

- **`overall`** — RMSE across all samples and axes pooled.
- **`mean`** — mean of the per-axis RMSE values.

`direction_agreement` ignores samples whose true velocity is exactly zero
(direction is undefined there).

## Open items (do not treat as settled)

1. **`active_speed_threshold_px_s = 5.0` is unvalidated.** It is a
   *development parameter*, not a frozen constant. It is an extra
   reference-domain filter, distinct from the frozen Stage 2.5
   `active_motion_flag` (sensor-domain: GYRO x/y L2 >= 0.1 rad/s, already on
   every grid row). Calibrate it on the real development cohort — e.g. by
   sweeping it and checking the qualification verdict is stable across a
   plausible range, rather than tuning it until the verdict flips.
2. **`development_users` / `evaluation_users` are empty.** The pipeline
   cannot run on real data until the roster is filled in.
3. `renca.txt` still writes `Y(t - tau)` while the implemented convention is
   `Y(t-tau)` via the grid — consistent in effect, but the wording should be
   reconciled with the frozen decision record.