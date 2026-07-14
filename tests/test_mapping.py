from __future__ import annotations

from pathlib import Path

import pytest

from vasp_cache.mapping import (
    content_hash,
    load_mapping,
    mapping_digest,
    soft_distance,
    soft_vector,
)
from conftest import write_minimal_inputs


class TestLoadMapping:
    def test_load_default_mapping(self):
        profile = load_mapping()
        assert isinstance(profile, dict)
        assert "key_generation" in profile

    def test_default_key_generation(self):
        profile = load_mapping()
        assert profile["key_generation"] == 1

    def test_default_has_hard_section(self):
        profile = load_mapping()
        assert "hard" in profile
        assert "incar" in profile["hard"]
        assert isinstance(profile["hard"]["incar"], list)

    def test_default_has_soft_section(self):
        profile = load_mapping()
        assert "soft" in profile
        assert "incar" in profile["soft"]
        assert isinstance(profile["soft"]["incar"], list)

    def test_default_hard_includes_encut(self):
        profile = load_mapping()
        assert "ENCUT" in profile["hard"]["incar"]

    def test_default_soft_includes_nsw(self):
        profile = load_mapping()
        assert "NSW" in profile["soft"]["incar"]

    def test_load_custom_mapping(self, tmp_path: Path):
        custom = tmp_path / "custom.yaml"
        custom.write_text("key_generation: 2\nhard:\n  incar: [ENCUT]\n  structure: false\n  kpoints: false\n  potcar: false\nsoft:\n  incar: []\n")
        profile = load_mapping(custom)
        assert profile["key_generation"] == 2
        assert profile["hard"]["incar"] == ["ENCUT"]


class TestMappingDigest:
    def test_digest_stable(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        h1 = mapping_digest(d)
        h2 = mapping_digest(d)
        assert h1 == h2

    def test_digest_includes_generation(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        h = mapping_digest(d)
        assert h.startswith("1:")

    def test_kpoints_change_flips_digest(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        h0 = mapping_digest(d)
        (d / "KPOINTS").write_text(
            "Automatic mesh\n0\nGamma\n2 2 2\n0 0 0\n"
        )
        assert mapping_digest(d) != h0

    def test_critical_incar_change_flips_digest(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        h0 = mapping_digest(d)
        (d / "INCAR").write_text("ENCUT = 600\nPREC = Normal\nISMEAR = -5\nSIGMA = 0.1\nISIF = 3\nGGA = PE\nLASPH = .TRUE.\n")
        assert mapping_digest(d) != h0

    def test_soft_incar_change_does_not_flip_digest(self, tmp_path: Path):
        """Only soft keys (NSW, NELM, ...) changed — hard hash stays same."""
        d = write_minimal_inputs(tmp_path / "a")
        h0 = mapping_digest(d)
        # NSW is soft; changing it should NOT affect the hard hash
        (d / "INCAR").write_text(
            "ENCUT = 520\nPREC = Normal\nISMEAR = -5\n"
            "SIGMA = 0.1\nISIF = 3\nGGA = PE\nLASPH = .TRUE.\n"
            "NSW = 200\nNELM = 100\n"
        )
        # Critical fields are unchanged, soft fields changed
        # The hard hash should remain the same
        h1 = mapping_digest(d)
        assert h0 == h1, "Adding soft-only NSW/NELM should not change hard hash"

    def test_empty_dir_still_returns_string(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()
        h = mapping_digest(d)
        assert isinstance(h, str)

    def test_digest_with_custom_mapping(self, tmp_path: Path):
        """Custom mapping with only structure + ENCUT in hard section."""
        d = write_minimal_inputs(tmp_path / "a")
        custom_map = {
            "key_generation": 2,
            "hard": {
                "incar": ["ENCUT"],
                "structure": True,
                "kpoints": False,
                "potcar": False,
            },
            "soft": {"incar": []},
        }
        h = mapping_digest(d, mapping=custom_map)
        assert h.startswith("2:")
        # Only structure + ENCUT contributed, no kpoints or potcar
        assert "444" not in h  # kpoints grid should not appear


class TestContentHash:
    def test_content_hash_accepts_no_mapping(self, tmp_path: Path):
        """content_hash without mapping falls back to legacy behavior."""
        d = write_minimal_inputs(tmp_path / "a")
        h = content_hash(d)
        assert isinstance(h, str)
        assert h  # non-empty

    def test_content_hash_with_mapping(self, tmp_path: Path):
        """content_hash with mapping applies generation prefix."""
        d = write_minimal_inputs(tmp_path / "a")
        h = content_hash(d)
        assert isinstance(h, str)
        # Default mapping means generation 1 prefix
        assert h.startswith("1:")

    def test_content_hash_from_mapping_differs_from_fingerprint(self, tmp_path: Path):
        """With default mapping, content_hash includes gen prefix vs plain fingerprint."""
        d = write_minimal_inputs(tmp_path / "a")
        from vasp_cache import content_hash as pkg_hash
        from vasp_cache.fingerprint import content_hash as fp_hash
        pkg = pkg_hash(d)
        fp = fp_hash(d)
        # Package hash includes gen prefix
        assert pkg == f"1:{fp}" or (pkg.startswith("1:") and pkg[2:] == fp)


class TestSoftVector:
    def test_soft_vector_returns_dict(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        sv = soft_vector(d)
        assert isinstance(sv, dict)

    def test_soft_vector_empty_by_default(self, tmp_path: Path):
        """Minimal INCAR has no soft keys."""
        d = write_minimal_inputs(tmp_path / "a")
        sv = soft_vector(d)
        # Minimal INCAR doesn't have NSW/NELM
        assert all(sv.get(k) is None for k in ("NSW", "NELM", "NELMIN", "EDIFF"))

    def test_soft_vector_with_soft_keys(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        (d / "INCAR").write_text(
            "ENCUT = 520\nNSW = 200\nNELM = 100\nEDIFF = 1E-4\n"
        )
        sv = soft_vector(d)
        assert sv.get("NSW") == 200
        assert sv.get("NELM") == 100
        assert sv.get("EDIFF") == "1E-4" or sv.get("EDIFF") == 0.0001

    def test_soft_vector_with_mapping(self, tmp_path: Path):
        d = write_minimal_inputs(tmp_path / "a")
        (d / "INCAR").write_text(
            "ENCUT = 520\nNSW = 200\n"
        )
        custom = {
            "key_generation": 1,
            "hard": {"incar": ["ENCUT"], "structure": True, "kpoints": True, "potcar": True},
            "soft": {"incar": ["NSW", "EDIFF"]},
        }
        sv = soft_vector(d, mapping=custom)
        assert sv.get("NSW") == 200


class TestSoftDistance:
    def test_same_vector_zero_distance(self):
        v = {"NSW": 100, "NELM": 60}
        assert soft_distance(v, v) == 0.0

    def test_different_vectors_positive_distance(self):
        v1 = {"NSW": 100, "NELM": 60}
        v2 = {"NSW": 200, "NELM": 120}
        d = soft_distance(v1, v2)
        assert d > 0

    def test_order_independent(self):
        v1 = {"NSW": 100, "NELM": 60}
        v2 = {"NSW": 200, "NELM": 120}
        assert soft_distance(v1, v2) == soft_distance(v2, v1)

    def test_empty_vectors(self):
        assert soft_distance({}, {}) == 0.0

    def test_missing_key_treated_as_none(self):
        v1 = {"NSW": 100}
        v2 = {"NSW": 100, "NELM": 60}
        # distance should handle missing keys gracefully
        d = soft_distance(v1, v2)
        assert isinstance(d, float)


class TestKeyGenerationPolicy:
    """Bump policy: critical edits require key_generation > default."""

    def test_soft_only_change_ok_without_bump(self, tmp_path: Path):
        """Changing only soft.incar does NOT require a generation bump."""
        custom = {
            "key_generation": 1,
            "hard": {
                "incar": ["ENCUT", "PREC", "ISMEAR", "SIGMA", "ISIF",
                          "LDAU", "LDAUTYPE", "LDAUU", "LDAUJ", "LDAUL",
                          "GGA", "IVDW", "LASPH", "METAGGA"],
                "structure": True,
                "kpoints": True,
                "potcar": True,
            },
            "soft": {"incar": ["NSW", "NELM"]},
        }
        d = write_minimal_inputs(tmp_path / "a")
        # This must not raise — soft-only change, same critical section
        h = content_hash(d, mapping=custom)
        assert h.startswith("1:")

    def test_critical_change_same_generation_raises(self):
        """Critical section differs but key_generation is NOT bumped."""
        custom = {
            "key_generation": 1,
            "hard": {
                "incar": ["ENCUT"],  # truncated vs default 14 keys
                "structure": False,
                "kpoints": False,
                "potcar": False,
            },
            "soft": {"incar": []},
        }
        with pytest.raises(ValueError, match="key_generation"):
            content_hash("/nonexistent", mapping=custom)

    def test_critical_change_with_bumped_generation_ok(self):
        """Critical section differs AND generation is bumped — allowed."""
        custom = {
            "key_generation": 2,
            "hard": {
                "incar": ["ENCUT"],
                "structure": False,
                "kpoints": False,
                "potcar": False,
            },
            "soft": {"incar": []},
        }
        # Must not raise
        h = content_hash("/nonexistent", mapping=custom)
        assert h.startswith("2:")

    def test_custom_yaml_without_bump_raises(self, tmp_path: Path):
        """Loading a custom YAML file with critical changes but no bump."""
        custom = tmp_path / "bad.yaml"
        custom.write_text(
            "key_generation: 1\n"
            "hard:\n  incar: [ENCUT]\n  structure: false\n  kpoints: false\n  potcar: false\n"
            "soft:\n  incar: []\n"
        )
        with pytest.raises(ValueError, match="key_generation"):
            load_mapping(custom)


    def test_identical_critical_yaml_accepts_same_generation(self, tmp_path: Path):
        """Mapping with exactly the same critical section as default is OK at gen=1."""
        default = [
            "ENCUT", "PREC", "ISMEAR", "SIGMA", "ISIF",
            "LDAU", "LDAUTYPE", "LDAUU", "LDAUJ", "LDAUL",
            "GGA", "IVDW", "LASPH", "METAGGA",
        ]
        custom = tmp_path / "same.yaml"
        lines = ["key_generation: 1", "hard:"]
        lines.append("  incar:")
        for k in default:
            lines.append(f"    - {k}")
        lines.append("  structure: true")
        lines.append("  kpoints: true")
        lines.append("  potcar: true")
        lines.append("soft:")
        lines.append("  incar: [NSW, NELM]")
        custom.write_text("\n".join(lines) + "\n")
        # Must not raise — critical section is identical to default
        profile = load_mapping(custom)
        assert profile["key_generation"] == 1
