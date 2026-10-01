"""Exact box-QP face enumeration: 3^3 faces per independent output axis."""

from itertools import product
import numpy as np


def solve_box_ridge(x, y, prior, lower, upper, ridge_lambda, condition_limit, tolerance):
    """Minimize mean(sum squared residuals) + lambda * ||theta-prior||^2.

    Every coordinate is free, at its lower bound, or at its upper bound.
    With lambda > 0 each output problem is strictly convex. Enumeration avoids
    convergence-budget ambiguity and is NOT clipping the unconstrained solution.
    """
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    prior, lower, upper = (np.asarray(a, dtype=np.float64) for a in (prior, lower, upper))
    if x.ndim != 2 or x.shape[1] != 3 or len(x) == 0 or y.shape != (len(x), 2):
        raise ValueError("invalid regression dimensions")
    if any(a.shape != (6,) for a in (prior, lower, upper)):
        raise ValueError("exactly six regression parameters required")
    if not all(np.isfinite(a).all() for a in (x, y, prior, lower, upper)):
        raise ValueError("nonfinite regression input")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            h = x.T @ x / len(x) + ridge_lambda * np.eye(3)
            condition = float(np.linalg.cond(h))
            if not np.isfinite(condition) or condition > condition_limit:
                raise ValueError("regularized system exceeds condition-number limit")
            theta = prior.copy()
            residuals = []
            for output, indices in enumerate(((0, 1, 4), (2, 3, 5))):
                ids = list(indices)
                p, lo, hi = prior[ids], lower[ids], upper[ids]
                rhs = x.T @ y[:, output] / len(x) + ridge_lambda * p
                best = None
                for states in product((-1, 0, 1), repeat=3):
                    free = [i for i, s in enumerate(states) if s == 0]
                    fixed = [i for i, s in enumerate(states) if s != 0]
                    candidate = np.array([lo[i] if s == -1 else hi[i] if s == 1 else 0.
                                          for i, s in enumerate(states)])
                    if free:
                        candidate[free] = np.linalg.solve(
                            h[np.ix_(free, free)], rhs[free] -
                            h[np.ix_(free, fixed)] @ candidate[fixed])
                    if np.any(candidate < lo) or np.any(candidate > hi):
                        continue
                    value = float(np.mean((x @ candidate - y[:, output]) ** 2) +
                                  ridge_lambda * np.sum((candidate - p) ** 2))
                    if best is None or value < best[0]:
                        best = value, candidate
                if best is None:
                    raise ValueError("no feasible bounded solution")
                candidate = best[1]
                grad = h @ candidate - rhs
                violation = np.where(candidate == lo, np.minimum(grad, 0),
                                     np.where(candidate == hi, np.maximum(grad, 0), grad))
                scale = max(1., float(np.max(np.abs(rhs))),
                            float(np.max(np.abs(h) @ np.abs(candidate))))
                kkt = float(np.max(np.abs(violation))) / scale
                if not np.isfinite(kkt) or kkt > tolerance:
                    raise ValueError("bounded solution failed scaled KKT tolerance")
                theta[ids] = candidate
                residuals.append(kkt)
            if not np.isfinite(theta).all():
                raise ValueError("nonfinite bounded solution")
            return theta.tolist(), {
                "regularized_condition_number": condition,
                "scaled_kkt_residual_by_output": residuals,
                "faces_per_output": 27,
            }
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise ValueError("numerically unsafe regression") from exc
