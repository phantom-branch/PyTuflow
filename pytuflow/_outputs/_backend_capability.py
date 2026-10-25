"""Explicit result-reader backend selection checks.

Default driver selection remains the responsibility of the existing readers.
Only an explicitly requested unavailable provider is rejected here, before
it can be mistaken for the runtime placeholder/stub implementation.
"""


def require_mesh_backend(
    driver: str,
    *,
    qgis_available: bool,
    h5py_available: bool,
    netcdf4_available: bool,
) -> None:
    """Raise a dependency-specific error for unavailable requested drivers."""
    selected = driver.lower()
    if (selected == "v1.0" or "qgis" in selected) and not qgis_available:
        raise ImportError(
            "QGIS Python bindings with the MDAL provider are required for "
            f"the explicitly selected {driver!r} mesh driver."
        )
    if "h5py" in selected and not h5py_available:
        raise ImportError(
            f"h5py is required for the explicitly selected {driver!r} mesh driver. "
            "Install h5py in the active Python environment."
        )
    if "netcdf4" in selected and not netcdf4_available:
        raise ImportError(
            f"netCDF4 is required for the explicitly selected {driver!r} mesh driver. "
            "Install netCDF4 in the active Python environment."
        )
