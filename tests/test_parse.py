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
        assert s["space_group"] is not None  # Fd-3m or Fd3m depending on symprec
        assert s["max_abc"] > 0
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


class TestPutIntegration:
    """Integration tests: put now fills richer doc from summarize_calc."""

    def test_put_uses_summary_fields(self, cache_root: Path, tmp_path: Path):
        """put() writes summary fields (bandgap, calc_type, etc.)."""
        from vasp_cache.api import put
        from vasp_cache.paths import get_project, _reset_project

        _reset_project()
        d = write_minimal_inputs(tmp_path / "calc")
        write_minimal_outcar(d, energy="-7.5", converged=True)
        ch = put(d)
        assert ch is not None

        job = get_project().open_job({"content_hash": ch})
        doc = job.doc
        # summary fields should be present
        assert "bandgap" in doc
        assert "calc_type" in doc
        assert "nsites" in doc
        assert "formula_pretty" in doc
        assert "space_group" in doc
        assert "tags" in doc
        assert "max_abc" in doc
        # override fields
        assert doc["formula"] == "Si"
        assert doc["task_name"] == "calc"
        assert doc["source_dir"] == str(d.resolve())
        assert "cached_at" in doc
        # mapping audit fields preserved
        assert "profile_id" in doc
        assert "key_generation" in doc
        assert "mapping_digest" in doc
