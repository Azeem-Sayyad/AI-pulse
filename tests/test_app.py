from streamlit.testing.v1 import AppTest


def _app():
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_demo_flow_end_to_end():
    at = _app()
    at.toggle[0].set_value(True).run()
    at.button[0].click().run()          # Load Demo Data
    assert not at.exception
    assert at.metric[0].value == "26"

    at.sidebar.radio[0].set_value("📝 Review & Edit").run()
    headline = at.text_input[0]
    headline.set_value("Edited live at the demo").run()
    approve_all = next(b for b in at.button if b.label.startswith("✅ Approve all"))
    approve_all.click().run()
    assert not at.exception

    at.sidebar.radio[0].set_value("📰 Generate Newsletter").run()
    at.button[0].click().run()          # Generate
    assert not at.exception
    assert "Edited live at the demo" in at.session_state.newsletter["html"]

    at.sidebar.radio[0].set_value("👁️ Preview").run()
    assert not at.exception
