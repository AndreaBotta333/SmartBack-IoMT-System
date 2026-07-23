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
        self.assertIn("/smartback-static/medical-portal.js", portal)
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
        self.assertIn('data-mode="night"', sessions)
        self.assertIn('data-session-id="night-1"', night)

    def test_main_does_not_contain_frontend_markup(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1] / "app" / "main.py"
        ).read_text(encoding="utf-8")
        for marker in ("<!doctype", "<html", "<style", "<script", "style="):
            self.assertNotIn(marker, main_source)


if __name__ == "__main__":
    unittest.main()
