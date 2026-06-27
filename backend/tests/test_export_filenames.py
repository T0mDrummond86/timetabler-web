from app.services.export_filenames import session_export_filename


def test_session_export_filename_uses_session_name_only_for_timetable():
    assert session_export_filename("Integrated Technologies S2 2026", ".xlsm") == (
        "Integrated Technologies S2 2026.xlsm"
    )


def test_session_export_filename_includes_label_for_other_exports():
    assert session_export_filename("My Session", ".xlsx", label="admin export") == (
        "My Session admin export.xlsx"
    )


def test_session_export_filename_strips_invalid_characters():
    assert session_export_filename('Bad/name:here?', ".json", label="backup") == (
        "Badnamehere backup.json"
    )


def test_session_export_filename_falls_back_when_empty():
    assert session_export_filename("   ", ".xlsx", label="warnings report") == (
        "session warnings report.xlsx"
    )
