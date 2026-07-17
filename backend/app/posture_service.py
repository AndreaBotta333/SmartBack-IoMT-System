"""Posture calculation, smoothing, calibration and threshold evaluation."""

import math
import threading
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ThresholdProfile:
    pitch_moderate_deg: float
    pitch_marked_deg: float
    roll_moderate_deg: float
    roll_marked_deg: float
    persistence_seconds: float

    def as_dict(self) -> dict[str, float]:
        return {
            # Legacy aliases consumed by the current mobile app.
            "moderate_deviation_deg": self.pitch_moderate_deg,
            "marked_deviation_deg": self.pitch_marked_deg,
            "moderate_pitch_deg": self.pitch_moderate_deg,
            "marked_pitch_deg": self.pitch_marked_deg,
            "moderate_roll_deg": self.roll_moderate_deg,
            "marked_roll_deg": self.roll_marked_deg,
            "persistence_seconds": self.persistence_seconds,
        }


@dataclass
class AxisState:
    moderate_active: bool = False
    marked_active: bool = False


@dataclass
class DevicePostureState:
    filtered_pitch_deg: float | None = None
    filtered_roll_deg: float | None = None
    reference_pitch_deg: float | None = None
    reference_roll_deg: float | None = None
    deviation_started_at: float | None = None
    pitch: AxisState = field(default_factory=AxisState)
    roll: AxisState = field(default_factory=AxisState)


def vector_pitch(x: float, y: float, z: float) -> float:
    return math.degrees(math.atan2(y, math.sqrt(x * x + z * z)))


def vector_roll(x: float, y: float, z: float) -> float:
    return math.degrees(math.atan2(x, math.sqrt(y * y + z * z)))


class PostureEngine:
    def __init__(
        self,
        profile_provider: Callable[[str], ThresholdProfile],
        *,
        ema_alpha: float,
        hysteresis_deg: float,
    ) -> None:
        if not 0 < ema_alpha <= 1:
            raise ValueError("ema_alpha must be in the interval (0, 1]")
        if hysteresis_deg < 0:
            raise ValueError("hysteresis_deg cannot be negative")
        self._profile_provider = profile_provider
        self._ema_alpha = ema_alpha
        self._hysteresis_deg = hysteresis_deg
        self._lock = threading.RLock()
        self._devices: dict[str, DevicePostureState] = {}

    @property
    def ema_alpha(self) -> float:
        return self._ema_alpha

    @property
    def hysteresis_deg(self) -> float:
        return self._hysteresis_deg

    def _axis_state(
        self,
        state: AxisState,
        absolute_deviation: float,
        moderate_threshold: float,
        marked_threshold: float,
    ) -> None:
        state.moderate_active = (
            absolute_deviation > max(0.0, moderate_threshold - self._hysteresis_deg)
            if state.moderate_active
            else absolute_deviation >= moderate_threshold
        )
        state.marked_active = (
            absolute_deviation > max(0.0, marked_threshold - self._hysteresis_deg)
            if state.marked_active
            else absolute_deviation >= marked_threshold
        )
        if not state.moderate_active:
            state.marked_active = False

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        device_id = str(payload["device_id"])
        patient_id = str(payload["patient_id"])
        timestamp_ms = int(payload["timestamp"])
        raw_pitch = vector_pitch(float(payload["x"]), float(payload["y"]), float(payload["z"]))
        raw_roll = vector_roll(float(payload["x"]), float(payload["y"]), float(payload["z"]))
        profile = self._profile_provider(patient_id)

        with self._lock:
            state = self._devices.setdefault(device_id, DevicePostureState())
            previous_pitch = state.filtered_pitch_deg if state.filtered_pitch_deg is not None else raw_pitch
            previous_roll = state.filtered_roll_deg if state.filtered_roll_deg is not None else raw_roll
            pitch = self._ema_alpha * raw_pitch + (1 - self._ema_alpha) * previous_pitch
            roll = self._ema_alpha * raw_roll + (1 - self._ema_alpha) * previous_roll
            state.filtered_pitch_deg = pitch
            state.filtered_roll_deg = roll

            if state.reference_pitch_deg is None:
                state.reference_pitch_deg = pitch
            if state.reference_roll_deg is None:
                state.reference_roll_deg = roll

            pitch_deviation = pitch - state.reference_pitch_deg
            roll_deviation = roll - state.reference_roll_deg
            self._axis_state(
                state.pitch,
                abs(pitch_deviation),
                profile.pitch_moderate_deg,
                profile.pitch_marked_deg,
            )
            self._axis_state(
                state.roll,
                abs(roll_deviation),
                profile.roll_moderate_deg,
                profile.roll_marked_deg,
            )

            moderate_active = state.pitch.moderate_active or state.roll.moderate_active
            marked_active = state.pitch.marked_active or state.roll.marked_active
            if moderate_active:
                if state.deviation_started_at is None:
                    state.deviation_started_at = timestamp_ms / 1000
            else:
                state.deviation_started_at = None
            duration = (
                max(0.0, timestamp_ms / 1000 - state.deviation_started_at)
                if state.deviation_started_at is not None
                else 0.0
            )

            dominant_axis = "pitch" if abs(pitch_deviation) >= abs(roll_deviation) else "roll"
            dominant_deviation = pitch_deviation if dominant_axis == "pitch" else roll_deviation

            if marked_active and duration >= profile.persistence_seconds:
                status, alert = "marked_deviation", "POSTURE_MARKED_DEVIATION"
            elif moderate_active and duration >= profile.persistence_seconds:
                status, alert = "prolonged_deviation", "POSTURE_PROLONGED_DEVIATION"
            elif moderate_active:
                status, alert = "deviated", None
            else:
                status, alert = "neutral", None

            return {
                **payload,
                "raw_pitch_deg": round(raw_pitch, 2),
                "raw_roll_deg": round(raw_roll, 2),
                "pitch_deg": round(pitch, 2),
                "roll_deg": round(roll, 2),
                "reference_pitch_deg": round(state.reference_pitch_deg, 2),
                "reference_roll_deg": round(state.reference_roll_deg, 2),
                "pitch_deviation_deg": round(pitch_deviation, 2),
                "roll_deviation_deg": round(roll_deviation, 2),
                # Backward-compatible dominant deviation used by the current app.
                "deviation_deg": round(dominant_deviation, 2),
                "dominant_axis": dominant_axis,
                "pitch_status": self._axis_label(state.pitch),
                "roll_status": self._axis_label(state.roll),
                "deviation_duration_seconds": round(duration, 1),
                "posture_status": status,
                "alert": alert,
                "threshold_profile": f"patient:{patient_id}",
                "thresholds": profile.as_dict(),
                "smoothing": {"method": "ema", "alpha": self._ema_alpha},
                "hysteresis_deg": self._hysteresis_deg,
            }

    @staticmethod
    def _axis_label(state: AxisState) -> str:
        if state.marked_active:
            return "marked"
        if state.moderate_active:
            return "moderate"
        return "neutral"

    def calibrate(self, device_id: str, sample: dict[str, Any]) -> dict[str, float | str]:
        with self._lock:
            state = self._devices.setdefault(device_id, DevicePostureState())
            state.reference_pitch_deg = float(sample["pitch_deg"])
            state.reference_roll_deg = float(sample["roll_deg"])
            state.deviation_started_at = None
            state.pitch = AxisState()
            state.roll = AxisState()
            return {
                "device_id": device_id,
                "reference_pitch_deg": round(state.reference_pitch_deg, 2),
                "reference_roll_deg": round(state.reference_roll_deg, 2),
            }
