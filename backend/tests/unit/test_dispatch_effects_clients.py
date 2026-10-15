from unittest.mock import Mock, call

from ill_bridge.jobs import dispatch_effects


def test_folio_clients_are_cached_per_tenant(monkeypatch):
    mdu_client = Mock()
    bth_client = Mock()
    factory = Mock(side_effect=[mdu_client, bth_client])
    monkeypatch.setattr(dispatch_effects, "_folio_clients", {})
    monkeypatch.setattr(dispatch_effects, "get_folio_client", factory)

    assert dispatch_effects._folio("mdu") is mdu_client
    assert dispatch_effects._folio("bth") is bth_client
    assert dispatch_effects._folio("mdu") is mdu_client
    assert dispatch_effects._folio("BTH") is bth_client
    assert factory.call_args_list == [call("mdu"), call("bth")]


def test_default_tenant_uses_its_own_cache_entry(monkeypatch):
    factory = Mock(side_effect=[Mock(), Mock()])
    monkeypatch.setattr(dispatch_effects, "_folio_clients", {})
    monkeypatch.setattr(dispatch_effects, "get_folio_client", factory)
    monkeypatch.setenv("ILL_TENANT_NAME", "mdu")

    mdu_client = dispatch_effects._folio()
    monkeypatch.setenv("ILL_TENANT_NAME", "bth")
    bth_client = dispatch_effects._folio()

    assert mdu_client is not bth_client
    assert dispatch_effects._folio("mdu") is mdu_client
    assert dispatch_effects._folio("bth") is bth_client
    assert factory.call_args_list == [call("mdu"), call("bth")]
