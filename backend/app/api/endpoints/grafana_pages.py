"""Pagine e controlli HTML incorporati nel portale Grafana."""

import html
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
)

from app.presentation import render_template
from app.repositories import CalibrationRepository
from app.services import AuthService, NightMonitoringService


def _session_options(
    choices: list[tuple[str, str, str, str]],
    selected_session: str,
) -> str:
    if not choices:
        return '<option value="">Nessuna sessione disponibile</option>'
    return "".join(
        f'<option value="{html.escape(value, quote=True)}" '
        f'data-start="{html.escape(start, quote=True)}" '
        f'data-stop="{html.escape(stop, quote=True)}"'
        f'{" selected" if value == selected_session else ""}>'
        f"{html.escape(label)}</option>"
        for label, value, start, stop in choices
    )


def register_grafana_page_endpoints(
    router: APIRouter,
    *,
    cookie_name: str,
    logo_candidates: tuple[Path, ...],
    calibration_algorithm_version: int,
    grafana_user_provider: Callable[[str | None], sqlite3.Row],
    patient_by_code: Callable[[sqlite3.Row, str], sqlite3.Row],
    calibration_repository_provider: Callable[
        [], CalibrationRepository
    ],
    day_sessions_provider: Callable[[str], list[dict]],
    night_service_provider: Callable[[], NightMonitoringService],
    auth_service_provider: Callable[[], AuthService],
) -> dict[str, Callable]:
    @router.get("/grafana-login", response_class=HTMLResponse)
    def grafana_login_page():
        return render_template("grafana-login.html")

    @router.get(
        "/smartback-assets/logo.png",
        response_class=FileResponse,
        include_in_schema=False,
    )
    def smartback_logo():
        for candidate in logo_candidates:
            if candidate.is_file():
                return FileResponse(candidate, media_type="image/png")
        raise HTTPException(
            status_code=404,
            detail="Logo SmartBack non disponibile",
        )

    @router.get("/smartback/", response_class=HTMLResponse)
    def medical_portal_page(
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        try:
            user = grafana_user_provider(smartback_grafana_session)
        except HTTPException:
            return RedirectResponse(url="/grafana-login", status_code=303)
        return render_template(
            "medical-portal.html",
            doctor_name=html.escape(str(user["name"])),
        )

    @router.get(
        "/api/v1/grafana/patients/{patient_code}/calibration-control",
        response_class=HTMLResponse,
    )
    def grafana_calibration_control(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        repository = calibration_repository_provider()
        device_id = repository.active_device(str(patient["id"]))
        current = (
            repository.reference_for_patient_device(
                device_id,
                str(patient["id"]),
                calibration_algorithm_version,
            )
            if device_id is not None
            else None
        )
        pitch = float(current["reference_pitch_deg"]) if current else 0.0
        roll = float(current["reference_roll_deg"]) if current else 0.0
        return HTMLResponse(
            render_template(
                "calibration-control.html",
                patient_code=html.escape(patient_code, quote=True),
                pitch=f"{pitch:.1f}",
                roll=f"{roll:.1f}",
            ),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate"
            },
        )

    @router.get(
        "/api/v1/grafana/patients/{patient_code}/alert-session-control",
        response_class=HTMLResponse,
    )
    def grafana_alert_session_control(
        patient_code: str,
        alert_day_start: str = "",
        session_id: str = "",
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        del alert_day_start
        user = grafana_user_provider(smartback_grafana_session)
        patient_by_code(user, patient_code)
        local_zone = ZoneInfo("Europe/Rome")
        choices = []
        for item in day_sessions_provider(patient_code):
            start = datetime.fromisoformat(item["start"])
            stop = datetime.fromisoformat(item["stop"])
            local_start = start.astimezone(local_zone)
            local_stop = stop.astimezone(local_zone)
            label = (
                f'{local_start.strftime("%d/%m/%y %H:%M:%S")} – '
                f'{local_stop.strftime("%H:%M:%S")}'
            )
            choices.append(
                (label, item["session_id"], item["start"], item["stop"])
            )
        return HTMLResponse(
            render_template(
                "session-control.html",
                current_session=html.escape(session_id, quote=True),
                mode="day",
                placeholder="Es. 20/07/26 oppure 10:30",
                options=_session_options(choices, session_id),
            ),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate"
            },
        )

    @router.get(
        "/api/v1/grafana/patients/{patient_code}/night-monitoring/control",
        response_class=HTMLResponse,
    )
    def grafana_night_monitoring_control(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        session = night_service_provider().active(str(patient["id"]))
        active = session is not None
        session_id = ""
        session_start_ms = ""
        if session is not None:
            started_at = datetime.fromisoformat(str(session["started_at"]))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            session_id = str(session["id"])
            session_start_ms = str(int(started_at.timestamp() * 1000))
        action = "stop" if active else "start"
        confirmation = (
            "Terminare la modalità notte per questo paziente?"
            if active
            else "Attivare la modalità notte per questo paziente?"
        )
        safe_patient = html.escape(patient_code, quote=True)
        return HTMLResponse(
            render_template(
                "night-monitoring-control.html",
                patient_code=safe_patient,
                active=str(active).lower(),
                confirmation=html.escape(confirmation, quote=True),
                session_id=html.escape(session_id, quote=True),
                session_start_ms=session_start_ms,
                action_url=(
                    f"/api/v1/grafana/patients/{safe_patient}/"
                    f"night-monitoring/{action}"
                ),
                button_class=action,
                button_text=(
                    "DISATTIVA MOD. NOTTE"
                    if active
                    else "ATTIVA MOD. NOTTE"
                ),
            )
        )

    @router.get(
        "/api/v1/grafana/patients/{patient_code}/night-session-control",
        response_class=HTMLResponse,
    )
    def grafana_night_session_control(
        patient_code: str,
        session_id: str = "",
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        items = night_service_provider().history(patient, 200)["items"]
        local_zone = ZoneInfo("Europe/Rome")
        choices: list[tuple[str, str, str, str]] = []
        for item in items:
            start = datetime.fromisoformat(str(item["started_at"]))
            stop = (
                datetime.fromisoformat(str(item["ended_at"]))
                if item["ended_at"]
                else datetime.now(timezone.utc)
            )
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if stop.tzinfo is None:
                stop = stop.replace(tzinfo=timezone.utc)
            local_start = start.astimezone(local_zone)
            local_stop = stop.astimezone(local_zone)
            label = (
                f'{local_start.strftime("%d/%m/%y %H:%M:%S")} – '
                f'{local_stop.strftime("%H:%M:%S")}'
            )
            choices.append(
                (
                    label,
                    str(item["id"]),
                    start.isoformat(),
                    stop.isoformat(),
                )
            )
        return HTMLResponse(
            render_template(
                "session-control.html",
                current_session=html.escape(session_id, quote=True),
                mode="night",
                placeholder="Es. 21/07/26 oppure 02:30",
                options=_session_options(choices, session_id),
            ),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate"
            },
        )

    @router.get("/grafana-calibration", response_class=HTMLResponse)
    def grafana_calibration_page(
        patient_id: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_id)
        current = calibration_repository_provider().latest_for_patient(
            str(patient["id"]),
            calibration_algorithm_version,
        )
        current_reference = (
            "Nessuna calibrazione salvata"
            if current is None
            else (
                f"Pitch {float(current['reference_pitch_deg']):.1f}° · "
                f"Roll {float(current['reference_roll_deg']):.1f}°"
            )
        )
        safe_patient = html.escape(patient_id, quote=True)
        monitoring_url = (
            "/grafana/d/smartback-overview/"
            "smartback-monitoraggio-paziente"
            f"?var-patient_id={safe_patient}&refresh=1s"
        )
        return render_template(
            "calibration-page.html",
            patient_code=safe_patient,
            current_reference=html.escape(current_reference),
            monitoring_url=monitoring_url,
        )

    @router.get("/grafana-logout")
    def grafana_browser_logout(
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        if smartback_grafana_session:
            auth_service_provider().logout(smartback_grafana_session)
        response = RedirectResponse(
            url="/grafana-login",
            status_code=303,
        )
        response.delete_cookie(cookie_name, path="/")
        response.headers["Clear-Site-Data"] = '"cookies"'
        response.headers["Cache-Control"] = "no-store"
        return response

    return {
        "grafana_login_page": grafana_login_page,
        "smartback_logo": smartback_logo,
        "medical_portal_page": medical_portal_page,
        "grafana_calibration_control": grafana_calibration_control,
        "grafana_alert_session_control": grafana_alert_session_control,
        "grafana_night_monitoring_control": (
            grafana_night_monitoring_control
        ),
        "grafana_night_session_control": grafana_night_session_control,
        "grafana_calibration_page": grafana_calibration_page,
        "grafana_browser_logout": grafana_browser_logout,
    }
