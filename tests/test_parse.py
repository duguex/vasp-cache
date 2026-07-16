"""Tests for vasp_cache.parse — summarize_calc and tag helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from vasp_cache.parse import MAX_LATTICE, summarize_calc
from conftest import write_minimal_inputs, write_minimal_outcar


class TestSummarizeCalc:
    """Tests for summarize_calc (TaskDoc → regex fallback)."""

    def test_regex_summary(self, tmp_path: Path):
        """Regex fallback extracts energy and converged flag."""
        d = write_minimal_inputs(tmp_path / "c")
        write_minimal_outcar(d, energy="-5.0", converged=True)
        s = summarize_calc(d)
        assert s["converged"] is True
        assert s["total_energy"] == -5.0
        assert s["parsed_by"] in {"regex", "TaskDoc"}

    def test_regex_converged_with_inputs(self, tmp_path: Path):
        """Full inputs → formula, nsites, space_group, tags populated."""
        src = tmp_path / "calc"
        write_minimal_inputs(src)
        write_minimal_outcar(src, energy="-12.5", converged=True)
        s = summarize_calc(src)
        assert s["converged"] is True
        assert s["total_energy"] == -12.5
        assert s["formula_pretty"] == "Si"
        assert s["nsites"] == 2
        # SpacegroupAnalyzer may fail on tiny synthetic cells; lattice/sites matter more
        assert s["max_abc"] > 0
        if s["space_group"] is not None:
            assert isinstance(s["space_group"], str)
        assert s["parsed_by"] in {"regex", "TaskDoc"}
        assert "Si2" in s["tags"]

    def test_regex_unconverged(self, tmp_path: Path):
        """Unconverged OUTCAR gives converged=False but still extracts energy."""
        src = tmp_path / "calc"
        src.mkdir()
        (src / "OUTCAR").write_text(
            " free  energy    TOTEN  =    -3.14 eV\n"
            "maximum number of electronic steps reached\n"
        )
        s = summarize_calc(src)
        assert s["converged"] is False
        assert s["total_energy"] == -3.14
        assert s["parsed_by"] == "regex"

    def test_no_outcar(self, tmp_path: Path):
        """No OUTCAR → safe defaults."""
        src = tmp_path / "empty"
        src.mkdir()
        s = summarize_calc(src)
        assert s["converged"] is False
        assert s["total_energy"] is None
        assert s["parsed_by"] == "fallback"

    def test_tags_from_incar(self, tmp_path: Path):
        """INCAR flags reflected in tags via regex path."""
        src = tmp_path / "calc"
        src.mkdir()
        write_minimal_outcar(src, energy="-5.0", converged=True)
        (src / "INCAR").write_text(
            "SYSTEM = test\nENCUT = 600\nLDAU = True\nISPIN = 2\n"
        )
        s = summarize_calc(src)
        assert s["parsed_by"] == "regex"
        tags = s["tags"]
        assert "DFT+U" in tags
        assert "spin" in tags
        assert "high-encut" in tags

    def test_tags_default_when_no_incar(self, tmp_path: Path):
        """No INCAR → tags is empty string (no incar parsed)."""
        src = tmp_path / "calc"
        src.mkdir()
        write_minimal_outcar(src, energy="-1.0", converged=True)
        s = summarize_calc(src)
        # Without INCAR, tags come from structure only
        assert s["tags"] == ""  # no structure → no tags
        assert s["parsed_by"] == "regex"

    def test_max_lattice_constant(self):
        """MAX_LATTICE is defined as 25.0."""
        assert MAX_LATTICE == 25.0


@pytest.mark.parametrize(
    ("incar", "expected"),
    [
        ("", {"nsw": 0, "ibrion": -1, "isif": 2}),
        ("NSW = 4\n", {"nsw": 4, "ibrion": 0, "isif": 0}),
        ("NSW = 4\nIBRION = 1\n", {"nsw": 4, "ibrion": 1, "isif": 2}),
        (
            "NSW = 4\nIBRION = 1\nLHFCALC = .TRUE.\n",
            {"nsw": 4, "ibrion": 1, "isif": 0},
        ),
    ],
)
def test_effective_incar_defaults(
    tmp_path: Path, incar: str, expected: dict[str, int]
):
    src = write_minimal_inputs(tmp_path / "calc")
    (src / "INCAR").write_text(incar)
    write_minimal_outcar(src, energy="-5.0", converged=True)
    summary = summarize_calc(src)
    assert {key: summary[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("incar", "expected"),
    [
        ("NSW = 4\nIBRION = 0\n", "sampled"),
        ("NSW = 4\nIBRION = 3\n", "sampled"),
        ("IBRION = 5\n", "sampled"),
        ("IBRION = 6\n", "sampled"),
        ("IBRION = 7\n", "sampled"),
        ("IBRION = 8\n", "sampled"),
        ("NSW = 4\nIBRION = 1\n", "canonical"),
        ("NSW = 4\nIBRION = 2\n", "canonical"),
        ("", "unknown"),
    ],
)
def test_provenance_classification(
    tmp_path: Path, incar: str, expected: str
):
    src = write_minimal_inputs(tmp_path / "calc")
    (src / "INCAR").write_text(incar)
    write_minimal_outcar(src, energy="-5.0", converged=True)
    summary = summarize_calc(src)
    assert summary["provenance"] == expected


def test_run_metadata_survives_successful_taskdoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class Output:
        energy = -5.0
        bandgap = None
        structure = None

    class Doc:
        state = "successful"
        output = Output()
        formula_pretty = "Si"
        nsites = 2
        symmetry = None
        calc_type = None
        run_type = None

    from emmet.core.tasks import TaskDoc

    monkeypatch.setattr(
        TaskDoc,
        "from_directory",
        lambda *_args, **_kwargs: Doc(),
    )
    src = write_minimal_inputs(tmp_path / "taskdoc")
    (src / "INCAR").write_text("NSW = 4\nIBRION = 0\n")
    write_minimal_outcar(src, energy="-5.0", converged=True)

    summary = summarize_calc(src)

    assert summary["parsed_by"] == "TaskDoc"
    assert summary["nsw"] == 4
    assert summary["ibrion"] == 0
    assert summary["provenance"] == "sampled"


def test_run_status_fields_are_independent(tmp_path: Path):
    src = write_minimal_inputs(tmp_path / "status")
    write_minimal_outcar(src, energy="-5.0", converged=True)
    summary = summarize_calc(src)
    assert summary["outcar_complete"] is True
    assert summary["electronic_converged"] is None
    assert summary["ionic_converged"] is None


class TestPutIntegration:
    """Integration tests: put now fills richer doc from summarize_calc."""

    def test_put_uses_summary_fields(self, cache_root: Path, tmp_path: Path):
        """put() writes summary fields (bandgap, calc_type, etc.)."""
        from vasp_cache.api import put
        from vasp_cache.meta import get_entry
        from vasp_cache.paths import _reset_project, cache_root as cr

        _reset_project()
        d = write_minimal_inputs(tmp_path / "calc")
        write_minimal_outcar(d, energy="-7.5", converged=True)
        ch = put(d)
        assert ch is not None

        doc = get_entry(cr(), ch)
        assert doc is not None
        assert "nsites" in doc
        assert "tags" in doc
        assert "max_abc" in doc
        assert doc["formula"] == "Si"
        assert doc["task_name"] == "calc"
        assert doc["source_dir"] == str(d.resolve())
        assert "cached_at" in doc
        assert "profile_id" in doc
        assert "key_generation" in doc
        assert "mapping_digest" in doc
