from types import SimpleNamespace

from lain_cli.prometheus import Alertmanager


def test_alertmanager_post_alerts_defaults(monkeypatch):
    alertmanager = Alertmanager("http://alert.example")
    calls = {}

    def fake_post(path, **kwargs):
        calls["path"] = path
        calls["kwargs"] = kwargs
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(alertmanager, "post", fake_post)

    result = alertmanager.post_alerts()

    assert result is None
    assert calls == {
        "path": "/api/v2/alerts",
        "kwargs": {
            "json": [
                {
                    "labels": {"label": "value"},
                    "annotations": {"label": "value"},
                    "generatorURL": "http://alert.example/<generating_expression>",
                }
            ]
        },
    }
