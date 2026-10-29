import pytest

from interlock_checker.pid_reader import PidReadError, read_pid
from interlock_checker.synthetic import build_pid_xml

from conftest import PUBLIC_C01


def test_synthetic_pid_tags_and_attributes(seeded_files):
    pid = read_pid(seeded_files[0])
    assert pid.get("FZT-101D").kind == "transmitter"
    assert pid.get("FZT-110").safety_class == "SIL2"
    assert pid.get("FZT-110").voting == "2oo3"
    assert pid.get("XV-170").fail_action == "FC"
    assert pid.get("XV-100").fail_action == "FL"
    assert pid.get("LV-130").fail_action == "FO"
    assert pid.get("FV-100").loop == "FIC-100"
    assert pid.get("F-101").kind == "equipment"
    assert pid.get("TZT-160") is None          # seeded: missing from the P&ID
    assert pid.warnings == []


def test_tag_matching_ignores_case_and_separators(seeded_files):
    pid = read_pid(seeded_files[0])
    assert pid.get("fzt 101a") is pid.get("FZT-101A")
    assert pid.get("XV_170") is pid.get("XV-170")


def test_clean_pid_has_the_extra_items(clean_files):
    pid = read_pid(clean_files[0])
    assert pid.get("TZT-160") is not None
    assert pid.get("XV-176").fail_action == "FC"
    assert pid.get("XV-172").fail_action == "FO"


@pytest.mark.skipif(not PUBLIC_C01.exists(), reason="run scripts/fetch_public_example.py first")
def test_public_dexpi_example():
    pid = read_pid(PUBLIC_C01)
    assert pid.get("P4711").kind == "equipment"
    assert pid.get("PT4712.01").kind == "transmitter"
    assert pid.get("PV4712.02").fail_action == "FC"
    assert pid.get("TV4750.03").fail_action == "FO"


def test_missing_file(tmp_path):
    with pytest.raises(PidReadError, match="not found"):
        read_pid(tmp_path / "nope.xml")


def test_not_xml(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("this is not xml")
    with pytest.raises(PidReadError, match="Could not read"):
        read_pid(bad)


_INFO = ('<PlantInformation Application="Dexpi" ApplicationVersion="1.3.1" Date="2026-01-01" '
         'Discipline="PID" Is3D="no" OriginatingSystem="t" OriginatingSystemVendor="t" '
         'OriginatingSystemVersion="1" SchemaVersion="4.1.1" Time="00:00:00" Units="mm"/>')


def test_xml_that_is_not_dexpi(tmp_path):
    f = tmp_path / "page.xml"
    f.write_text("<html><body>hello</body></html>")
    with pytest.raises(PidReadError, match="PlantInformation"):
        read_pid(f)


def test_dexpi_without_tags(tmp_path):
    f = tmp_path / "empty.xml"
    f.write_text(f'<?xml version="1.0"?><PlantModel>{_INFO}</PlantModel>')
    with pytest.raises(PidReadError, match="nothing to check"):
        read_pid(f)


def test_pydexpi_errors_are_passed_on(tmp_path):
    f = tmp_path / "odd.xml"
    f.write_text(
        f'<?xml version="1.0"?><PlantModel>{_INFO}'
        '<ActuatingSystem ID="A1" ComponentClass="ActuatingSystem"><GenericAttributes Set="DexpiAttributes">'
        '<GenericAttribute Name="ActuatingSystemNumberAssignmentClass" Value="XV-1"/></GenericAttributes>'
        '<ActuatingSystemComponent ID="C1" ComponentClass="ControlledActuator">'
        '<GenericAttributes Set="DexpiAttributes">'
        '<GenericAttribute Name="FailActionSpecialization" Value="FailSideways"/>'
        '</GenericAttributes></ActuatingSystemComponent></ActuatingSystem></PlantModel>')
    pid = read_pid(f)
    assert pid.get("XV-1").fail_action is None
    assert any("FailSideways" in w for w in pid.warnings)


def test_generator_output_round_trips(tmp_path):
    f = tmp_path / "p.xml"
    f.write_bytes(build_pid_xml(seeded=False))
    assert read_pid(f).get("XV-176") is not None
