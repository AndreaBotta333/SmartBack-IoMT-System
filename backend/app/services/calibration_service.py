"""Casi d'uso per calibrazione live e calibrazione manuale."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.repositories.calibration_repository import CalibrationRepository


class CalibrationConflict(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class CalibrationService:
    def __init__(
        self,
        repository: CalibrationRepository,
        *,
        mqtt: object | None,
        influx: object | None,
        posture_engine: object | None,
        stale_seconds: float,
        algorithm_version: int,
        threshold_provider: Callable[[Any], Any],
        pending_samples: dict[tuple[str, str], dict[str, Any]],
    ):
        self.repository = repository
        self.mqtt = mqtt
        self.influx = influx
        self.posture_engine = posture_engine
        self.stale_seconds = stale_seconds
        self.algorithm_version = algorithm_version
        self.threshold_provider = threshold_provider
        self.pending_samples = pending_samples

    def fresh_sample(
        self, patient_code: str, device_id: str | None = None
    ) -> dict[str, Any]:
        sample = self.mqtt.latest_posture if self.mqtt else None
        if sample is None or sample.get("patient_id") != patient_code:
            raise CalibrationConflict("La maglia del paziente non sta trasmettendo")
        if device_id is not None and sample.get("device_id") != device_id:
            raise CalibrationConflict("Nessun campione corrente per questo dispositivo")
        age = max(
            0.0,
            datetime.now(timezone.utc).timestamp()
            - float(sample["timestamp"]) / 1000,
        )
        if age > self.stale_seconds:
            raise CalibrationConflict(
                "Dati troppo vecchi: riconnetti la maglia prima di calibrare"
            )
        return sample

    def capture(self, user_id: str, patient_code: str) -> None:
        self.pending_samples[(user_id, patient_code)] = {
            "sample": dict(self.fresh_sample(patient_code)),
            "captured_at": datetime.now(timezone.utc),
        }

    def consume_capture(self, user_id: str, patient_code: str) -> dict[str, Any]:
        pending = self.pending_samples.pop((user_id, patient_code), None)
        if pending is None:
            raise CalibrationConflict(
                "Campione di calibrazione assente: premi nuovamente CALIBRA"
            )
        if datetime.now(timezone.utc) - pending["captured_at"] > timedelta(minutes=2):
            raise CalibrationConflict(
                "Campione di calibrazione scaduto: premi nuovamente CALIBRA"
            )
        return pending["sample"]

    def calibrate(
        self, *, patient: Any, calibrated_by: Any, patient_code: str,
        device_id: str | None = None,
        captured_sample: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sample = captured_sample or self.fresh_sample(patient_code, device_id)
        if sample.get("patient_id") != patient_code:
            raise CalibrationConflict(
                "Il campione acquisito appartiene a un altro paziente"
            )
        if device_id is not None and sample.get("device_id") != device_id:
            raise CalibrationConflict(
                "Il campione acquisito appartiene a un altro dispositivo"
            )
        try:
            result = (
                self.mqtt.calibrate_from_sample(str(sample["device_id"]), sample)
                if captured_sample is not None
                else self.mqtt.calibrate(str(sample["device_id"]))
            )
        except LookupError as error:
            raise CalibrationConflict(
                "Il campione corrente non è più disponibile: riprova la calibrazione"
            ) from error
        return self._persist(
            patient, calibrated_by, patient_code, sample, result
        )

    def manual(
        self, *, patient: Any, calibrated_by: Any, patient_code: str,
        pitch_deg: float | None, roll_deg: float | None,
    ) -> dict[str, Any]:
        device_id = self.repository.active_device(str(patient["id"]))
        if device_id is None:
            raise CalibrationConflict(
                "Nessuna maglia attiva assegnata al paziente"
            )
        current = self.repository.reference_for_patient_device(
            device_id, str(patient["id"]), self.algorithm_version
        )
        pitch = float(pitch_deg) if pitch_deg is not None else (
            float(current["reference_pitch_deg"]) if current else 0.0
        )
        roll = float(roll_deg) if roll_deg is not None else (
            float(current["reference_roll_deg"]) if current else 0.0
        )
        result = {
            "device_id": device_id,
            "reference_pitch_deg": round(pitch, 2),
            "reference_roll_deg": round(roll, 2),
        }
        if self.posture_engine is not None:
            result = self.posture_engine.calibrate(
                device_id, {"pitch_deg": pitch, "roll_deg": roll}
            )
        return self._persist(
            patient, calibrated_by, patient_code,
            {"pitch_deg": pitch, "roll_deg": roll}, result,
        )

    def _persist(
        self, patient: Any, calibrated_by: Any, patient_code: str,
        sample: dict[str, Any], result: dict[str, Any],
    ) -> dict[str, Any]:
        self.repository.save(
            patient_id=str(patient["id"]),
            calibrated_by=str(calibrated_by["id"]),
            result=result,
            algorithm_version=self.algorithm_version,
        )
        if self.influx is not None:
            self.influx.persist_calibration_reference(
                device_id=str(result["device_id"]),
                patient_code=patient_code,
                reference_pitch_deg=float(result["reference_pitch_deg"]),
                reference_roll_deg=float(result["reference_roll_deg"]),
                selected_pitch_deg=float(sample["pitch_deg"]),
                selected_roll_deg=float(sample["roll_deg"]),
            )
        return {
            **result,
            "patient_id": patient["id"],
            "patient_code": patient_code,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": self.threshold_provider(patient).as_dict(),
        }
