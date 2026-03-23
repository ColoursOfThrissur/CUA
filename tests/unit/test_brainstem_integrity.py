import importlib


def test_brainstem_integrity_status_is_configured():
    module = importlib.import_module("core.immutable_brain_stem")

    status = module.BrainStem.get_integrity_status()

    assert status["configured"] is True
    assert status["current_checksum"] == status["expected_checksum"]
    assert status["valid"] is True
