"""Nested user-wise validation for L0.

Outer loop : leave-one-user-out over development participants.
Inner loop : grouped K-fold over the remaining participants, grouped by
             participant_code.

Contamination rules enforced here:
  * the scaler is refitted from inner TRAINING users for every inner
    fold, so an outer validation user never contributes statistics;
  * the window candidate is chosen on inner folds only;
  * fold assignments are returned so the split is auditable and
    reproducible rather than implicit.
"""

from dataclasses import dataclass

import numpy as np

from .dataset import (
    L0WindowDataset, StandardScaler, build_l0_datasets, concatenate_users)
from .metrics import active_mask, direction_agreement, mae, rmse
from .train_l0 import fit_dataset, predict


@dataclass(frozen=True)
class FoldAssignment:
    outer_validation_user: str
    inner_fold: int
    train_users: tuple
    validation_users: tuple


def grouped_k_fold(users, folds):
    """Deterministic grouped K-fold over participant codes.

    Grouped so that all windows of a participant stay together. Users are
    ordered by code before rounding-robin assignment, which makes the
    split independent of dict ordering or input row order.
    """
    unique = sorted(set(str(user) for user in users))
    folds = int(folds)
    if folds < 2:
        raise ValueError("inner_folds must be at least 2")
    if len(unique) < folds:
        raise ValueError(
            f"cannot build {folds} grouped folds from {len(unique)} users")
    assignment = {}
    for position, user in enumerate(unique):
        assignment[user] = position % folds
    return [
        (index, [u for u in unique if assignment[u] == index])
        for index in range(folds)
    ]


def _dataset_for(built, train_users, validation_users):
    """Fit the scaler on train_users, then attach it to both splits."""
    X_train, y_train, codes_train, active_train = concatenate_users(
        built, train_users)
    scaler = StandardScaler().fit(X_train)
    train = L0WindowDataset(
        X_train, y_train, codes_train, active_train, scaler=scaler)
    X_val, y_val, codes_val, active_val = concatenate_users(
        built, validation_users)
    validation = L0WindowDataset(
        X_val, y_val, codes_val, active_val, scaler=scaler)
    return train, validation


def _score(y_true, y_pred, active, config):
    threshold = config.qualification.active_speed_threshold_px_s
    mask = active_mask(y_true, active, threshold)
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "direction_agreement": direction_agreement(y_true, y_pred, mask),
        "active_samples": int(mask.sum()),
        "samples": int(len(y_true)),
    }


def select_window(config, built, outer_user, remaining_users):
    """Choose the window candidate using inner folds only.

    Selection criterion is inner mean RMSE in px/s. The outer validation
    user is absent from every inner split by construction.
    """
    folds = grouped_k_fold(remaining_users, config.validation.inner_folds)
    scores = {}
    for window in config.window_candidates:
        fold_rmse, assignments = [], []
        for index, validation_users in folds:
            train_users = [u for u in remaining_users
                           if u not in set(validation_users)]
            if not train_users:
                continue
            train, inner_val = _dataset_for(built, train_users, validation_users)
            result = fit_dataset(
                config, train, window,
                seed=config.seed + index)
            y_true, y_pred, _, active = predict(result.model, inner_val)
            score = _score(y_true, y_pred, active, config)
            fold_rmse.append(score["rmse"]["mean"])
            assignments.append(
                FoldAssignment(
                    outer_validation_user=outer_user, inner_fold=index,
                    train_users=tuple(sorted(train_users)),
                    validation_users=tuple(sorted(validation_users))))
        scores[window] = {
            "mean_rmse_px_s": float(np.mean(fold_rmse)) if fold_rmse else None,
            "folds": assignments,
        }
    scored = {w: v["mean_rmse_px_s"] for w, v in scores.items()
              if v["mean_rmse_px_s"] is not None}
    if not scored:
        raise ValueError("no inner fold produced a score")
    best = min(sorted(scored), key=lambda w: scored[w])
    return best, scores


def nested_user_wise_validation(config, rows, grid_interval_ns):
    """Full nested LOUO sweep over the development cohort.

    Returns a report containing the per-outer-user scores, the window
    selected on inner folds only, and every fold assignment.
    """
    development = list(config.require_development_users())
    if len(development) < 3:
        raise ValueError(
            f"nested user-wise validation needs at least 3 development "
            f"users, got {len(development)}")
    assignments, outer_scores = [], {}
    # Windows are built for every development user, including the one
    # currently held out; the scaler is still fitted only on training
    # users, so holding a user out means excluding it from fitting and
    # training, not from feature construction.
    built = build_l0_datasets(
        rows, max(config.window_candidates), grid_interval_ns, development)
    for outer_user in sorted(development):
        remaining = [u for u in development if u != outer_user]
        best_window, window_scores = select_window(
            config, built, outer_user, remaining)

        # Final refit on every remaining user; the outer user stays out.
        train, outer_val = _dataset_for(built, remaining, [outer_user])
        final = fit_dataset(config, train, best_window, seed=config.seed)
        y_true, y_pred, _, active = predict(final.model, outer_val)
        score = _score(y_true, y_pred, active, config)
        score["selected_window"] = int(best_window)
        score["window_scores"] = {
            str(w): window_scores[w]["mean_rmse_px_s"]
            for w in sorted(window_scores)}
        outer_scores[outer_user] = score
        for window in config.window_candidates:
            for fold in window_scores[window]["folds"]:
                assignments.append(fold)

    all_active = sum(s["active_samples"] for s in outer_scores.values())
    aggregate = {
        "mean_mae_px_s": float(np.mean(
            [s["mae"]["mean"] for s in outer_scores.values()])),
        "mean_rmse_px_s": float(np.mean(
            [s["rmse"]["mean"] for s in outer_scores.values()])),
        "mean_direction_agreement": float(np.mean(
            [s["direction_agreement"]["mean"] for s in outer_scores.values()])),
        "total_active_samples": int(all_active),
        "users": len(outer_scores),
    }
    return {
        "strategy": config.validation.strategy,
        "outer": "leave_one_user_out",
        "inner": "grouped_kfold",
        "inner_folds": config.validation.inner_folds,
        "development_users": sorted(development),
        "scaler_fit_scope": config.validation.scaler_fit_scope,
        "window_candidates": list(config.window_candidates),
        "per_user": outer_scores,
        "aggregate": aggregate,
        "fold_assignments": [
            {"outer_validation_user": a.outer_validation_user,
             "inner_fold": a.inner_fold,
             "train_users": list(a.train_users),
             "validation_users": list(a.validation_users)}
            for a in assignments],
    }

