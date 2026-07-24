"""Test del rendering dei template e degli asset del portale medico."""

from pathlib import Path
import unittest

from app.presentation import render_template


class PresentationTemplateTests(unittest.TestCase):
    def test_login_and_portal_load_external_assets(self) -> None:
        login = render_template("grafana-login.html")
        portal = render_template(
            "medical-portal.html",
            doctor_name="Medico Test",
        )

        self.assertIn("/smartback-static/grafana-login.js", login)
        self.assertIn("/smartback-static/medical-portal.js?v=4", portal)
        self.assertIn('type="module"', portal)
        self.assertIn("Medico Test", portal)
        self.assertNotIn("<style", login)
        self.assertNotIn("<script>", portal)

    def test_embedded_controls_render_all_dynamic_values(self) -> None:
        calibration = render_template(
            "calibration-control.html",
            patient_code="patient-1",
            pitch="-15.0",
            roll="3.0",
        )
        sessions = render_template(
            "session-control.html",
            current_session="session-1",
            mode="night",
            placeholder="Cerca",
            options='<option value="session-1">Sessione</option>',
        )
        night = render_template(
            "night-monitoring-control.html",
            patient_code="patient-1",
            active="true",
            confirmation="Confermare?",
            session_id="night-1",
            session_start_ms="1000",
            action_url="/stop",
            button_class="stop",
            button_text="DISATTIVA",
        )

        self.assertIn('data-patient="patient-1"', calibration)
        self.assertIn("/smartback-static/calibration-control.js?v=3", calibration)
        self.assertIn('data-mode="night"', sessions)
        self.assertIn('data-session-id="night-1"', night)
        self.assertIn("/smartback-static/night-monitoring-control.js?v=3", night)

    def test_grafana_controls_do_not_use_native_browser_popups(self) -> None:
        static_directory = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "presentation"
            / "static"
        )
        for filename in (
            "medical-portal.js",
            "calibration-control.js",
            "night-monitoring-control.js",
        ):
            script = (static_directory / filename).read_text(encoding="utf-8")
            self.assertNotIn("window.confirm(", script)
            self.assertNotIn("window.alert(", script)
            self.assertNotRegex(script, r"(?<![\w.])confirm\(")
            self.assertNotRegex(script, r"(?<![\w.])alert\(")

    def test_main_does_not_contain_frontend_markup(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1] / "app" / "main.py"
        ).read_text(encoding="utf-8")
        for marker in ("<!doctype", "<html", "<style", "<script", "style="):
            self.assertNotIn(marker, main_source)

    def test_home_preserves_selected_shirt_during_refresh(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "presentation"
            / "static"
            / "medical-portal.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const selectedShirts = new Map()", script)
        self.assertIn('localeCompare(', script)
        self.assertIn("patient.assigned_device_name", script)
        self.assertIn("const release = !device.available", script)
        self.assertNotIn('device.patient_name !== "Altro paziente"', script)
        self.assertIn('data-action="release-shirt"', script)
        self.assertIn('button[data-action]', script)
        self.assertNotIn("onclick=", script)

    def test_grafana_home_link_forces_a_full_navigation(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "presentation"
            / "static"
            / "grafana-navigation.js"
        ).read_text(encoding="utf-8")

        self.assertIn('"/grafana/smartback/"', script)
        self.assertIn("event.stopImmediatePropagation()", script)
        self.assertIn('window.location.assign(`/smartback/', script)


if __name__ == "__main__":
    unittest.main()
