from pathlib import Path

from streamlit.testing.v1 import AppTest

from runtime import Runtime


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_app_controls_and_downloads(monkeypatch, provider):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(
        Runtime, "_provider", lambda self, role, settings, payload: provider(role, settings, payload)
    )
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30)
    app.session_state["auto_run"] = False
    app.run()
    assert not app.exception
    app.number_input(key="generations").set_value(1)
    app.number_input(key="population").set_value(2)
    app.run()
    button(app, "Start Optimization").click().run()
    assert not app.exception
    before = app.session_state["runtime"].snapshot()["calls"]
    app.run()
    assert app.session_state["runtime"].snapshot()["calls"] == before
    assert app.text_area(key="base_prompt").disabled
    button(app, "Stop").click().run()
    assert app.session_state["stopped"]
    assert app.session_state["runtime"].snapshot()["calls"] == before
    button(app, "Resume").click().run()
    app.text_input(key="injection").set_value("Rewrite faithfully. Revision injected.")
    button(app, "Inject").click().run()
    for _ in range(3):
        button(app, "Run next stage").click().run()
        assert not app.exception
    assert app.session_state["state"]["phase"] == "finished"
    assert app.session_state["state"]["comparison"]["status"] == "complete"
    assert len(app.get("download_button")) >= 5
    button(app, "New run").click().run()
    assert app.session_state["runtime"] is None


def test_preparation_freezes_budget(monkeypatch, provider, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(
        Runtime, "_provider", lambda self, role, settings, payload: provider(role, settings, payload)
    )
    monkeypatch.setattr("benchmark.GENERATED_BENCHMARK_PATH", tmp_path / "benchmark.json")
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30)
    app.session_state["auto_run"] = False
    app.run()
    app.radio(key="benchmark_mode").set_value("Generate").run()
    button(app, "Prepare benchmark").click().run()
    assert not app.exception
    assert app.session_state["runtime"].snapshot()["calls"] == 1
    run_id = app.session_state["runtime"].run_id
    button(app, "Start Optimization").click().run()
    assert not app.exception
    assert app.session_state["runtime"].run_id == run_id
    assert app.session_state["runtime"].snapshot()["events"][0]["phase"] == "preparation"
