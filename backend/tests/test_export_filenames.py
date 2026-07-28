from app.services.export_filenames import content_disposition, session_export_filename


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


def test_content_disposition_survives_non_latin1_names():
    """HTTP headers are latin-1; an em dash used to blow up the whole export."""
    header = content_disposition("Tutorial sandbox — admin.xlsx")
    header.encode("latin-1")  # would raise UnicodeEncodeError before the fix
    assert 'filename="Tutorial sandbox - admin.xlsx"' in header
    assert "filename*=UTF-8''Tutorial%20sandbox%20%E2%80%94%20admin.xlsx" in header


def test_content_disposition_folds_accents_for_the_ascii_fallback():
    header = content_disposition("Café résumé.xlsx")
    header.encode("latin-1")
    assert 'filename="Cafe resume.xlsx"' in header


def test_content_disposition_falls_back_when_nothing_is_ascii():
    header = content_disposition("日本語.xlsx")
    header.encode("latin-1")
    assert 'filename="export.xlsx"' in header
    assert "filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E.xlsx" in header


def test_content_disposition_leaves_plain_names_alone():
    assert content_disposition("plain.xlsx") == (
        "attachment; filename=\"plain.xlsx\"; filename*=UTF-8''plain.xlsx"
    )
