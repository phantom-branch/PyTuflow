"""Explicit batch dependency collection and physical input validation for TUFLOW.

This module is the orchestration boundary; ordinary TCF parsing, Context and
single-run semantics remain unchanged. A batch uses one parsed TCF and the
existing immutable fragment collector before checking distinct physical files,
GeoPackage layers and ordinary BC CSV headers. It never launches TUFLOW.

Pass actual scheduled flags rather than generating a Cartesian product from
scenario/event names. Syntactic collection alone never opens physical inputs;
the separate validation phase is explicitly requested here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from os import PathLike
from time import perf_counter
from typing import TYPE_CHECKING

from .validation import (
    ValidationFinding,
    ValidationOptions,
    ValidationReport,
    validate_dependencies,
)

if TYPE_CHECKING:
    from ._tmf.cf.tcf import TCF
    from ._tmf.fragment_dependencies import FragmentBatchResult


@dataclass(frozen=True, slots=True)
class BatchValidationResult:
    """One immutable per-run dependency inventory and its physical findings."""

    dependencies: FragmentBatchResult
    validation: ValidationReport
    parse_seconds: float
    collection_seconds: float
    inspection_seconds: float

    @property
    def passed(self) -> bool:
        """Only a complete successful projection and inspection can pass."""
        return self.dependencies.passed and self.validation.passed

    @property
    def issues(self) -> tuple[ValidationFinding, ...]:
        """Missing, unresolved or unsupported files, layers and run contexts."""
        return tuple(
            item for item in self.validation.findings
            if item.status != "present"
        )


def validate_batch(
    model: TCF | str | PathLike[str],
    run_flags: Iterable[str | dict[str, str]],
    *,
    options: ValidationOptions | None = None,
) -> BatchValidationResult:
    """Check all syntactic references and selected physical inputs for runs.

    A caller may supply an already parsed TCF to avoid reopening control files.
    Files, filename wildcards, selected GeoPackage layers and BC CSV selectors
    are inspected only during the explicit validation phase. Every finding is
    attributed to its original run and owning command.

    Defaults are strict: check files and GeoPackage layers, validate ordinary
    BC CSV headers, and use the same filename-case policy as the parsed model.
    To inspect raster content or GIS feature attributes requires an additional
    explicit inspection capability; this function does not claim that a
    successfully present GIS layer certifies all of its feature-linked files.
    """
    from ._tmf.cf.tcf import TCF

    started = perf_counter()
    if isinstance(model, TCF):
        tcf = model
    else:
        # TUFLOW -cs policy must be applied while loading control files too.
        case = options.case_sensitivity if options is not None else None
        tcf = TCF(model, case_sensitivity=case)
    parse_seconds = perf_counter() - started

    policy = getattr(tcf.config, "case_sensitivity", None)
    if options is None:
        options = ValidationOptions(
            check_files=True,
            check_gpkg_layers=True,
            check_bc_csv_headers=True,
            case_sensitivity=policy,
        )
    elif options.case_sensitivity is None:
        # Do not silently use Linux's unknown case policy if the model has an
        # explicit TUFLOW case policy. Preserve every other requested option.
        options = replace(options, case_sensitivity=policy)
    elif policy is not None and options.case_sensitivity != policy:
        raise ValueError(
            "Validation case_sensitivity must match the parsed TCF policy"
        )

    started = perf_counter()
    dependencies = tcf.collect_file_dependencies(run_flags)
    collection_seconds = perf_counter() - started

    started = perf_counter()
    report = validate_dependencies(dependencies, options=options)
    inspection_seconds = perf_counter() - started

    return BatchValidationResult(
        dependencies, report,
        parse_seconds, collection_seconds, inspection_seconds,
    )
