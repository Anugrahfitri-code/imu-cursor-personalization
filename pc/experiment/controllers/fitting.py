"""Offline P2C fit. Nondeterministic timing is deliberately outside the adapter."""

from time import perf_counter_ns
import platform
import numpy as np

from .config import PARAMETER_NAMES, sha256
from .data import calibration_arrays, validate_bundle
from .solver import solve_box_ridge


def fit_p2c(bundle, config, declaration):
    started = perf_counter_ns()
    rows, provenance = validate_bundle(bundle, config, declaration)
    x, y, indices, counts = calibration_arrays(rows, config)
    solver_started = perf_counter_ns()
    theta, diagnostics = solve_box_ridge(
        x, y, config.theta0, config.lower_bounds, config.upper_bounds,
        config.ridge_lambda, config.condition_number_limit, config.kkt_tolerance)
    solver_finished = perf_counter_ns()
    x, y = np.asarray(x), np.asarray(y)

    def loss(parameters):
        coefficients = np.array([[parameters[0], parameters[2]],
                                 [parameters[1], parameters[3]],
                                 [parameters[4], parameters[5]]])
        return float(np.mean(np.sum((x @ coefficients - y) ** 2, axis=1)))

    mse_prior, mse_fit = loss(config.theta0), loss(theta)
    objective = mse_fit + config.ridge_lambda * float(
        np.sum((np.asarray(theta) - config.theta0) ** 2))
    if not np.isfinite(objective) or objective > mse_prior + config.kkt_tolerance * max(1., mse_prior):
        raise ValueError("fit objective is nonfinite or worse than feasible prior")
    body = {
        "schema_version": "stage2.6-adapter-v1",
        "condition": "P2C",
        "status": "DEVELOPMENT_CANDIDATE",
        "controller_config_sha256": config.sha256,
        "parameter_names": list(PARAMETER_NAMES),
        "theta": theta,
        "provenance": provenance,
        "selection": {
            "policy": "ALL_SENSOR_AND_LABEL_VALID_ROWS_IN_2C_INCLUDING_HOLDS",
            "selected_grid_indices_sha256": sha256(indices),
            "selected_row_count": len(indices), "total_row_count": len(rows),
            "valid_samples_per_sequence": counts,
        },
        "fit": {
            "solver": "BOX_RIDGE_FACE_ENUMERATION_FLOAT64_V1",
            "objective": "MEAN_SQUARED_VECTOR_ERROR_PLUS_L2_TO_PRIOR",
            "calibration_mse_prior": mse_prior, "calibration_mse_fit": mse_fit,
            "penalized_objective": objective, **diagnostics,
        },
        "numeric_environment": {"numpy": np.__version__, "python": platform.python_version()},
    }
    adapter = {**body, "adapter_sha256": sha256(body)}
    timing = {
        "schema_version": "stage2.6-adaptation-timing-v1",
        "adapter_sha256": adapter["adapter_sha256"],
        "clock": "perf_counter_ns",
        "solver_elapsed_ns": solver_finished - solver_started,
        "adaptation_elapsed_ns": perf_counter_ns() - started,
        "scope": "bundle validation + row selection + solver + adapter construction; excludes file IO",
    }
    return adapter, timing
