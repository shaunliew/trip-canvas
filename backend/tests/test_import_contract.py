def test_backend_modules_import_from_repo_root() -> None:
    import backend.main  # noqa: F401
    import backend.spike_agentic_payments  # noqa: F401
    import backend.spike_planner  # noqa: F401
