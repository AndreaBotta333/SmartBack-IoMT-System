"""Night-position classification independent from daytime posture thresholds."""

import math
import threading
from dataclasses import dataclass
from typing import Any, Callable


SessionProvider = Callable[[str, str], dict[str, str] | None]
SummaryUpdater = Callable[[str, str, float, bool], None]
PositionPersister = Callable[[dict[str, Any]], None]


@dataclass
class NightState:
    filtered_x: float | None = None
    filtered_y: float | None = None
    filtered_z: float | None = None
    position: str = "unknown"
    candidate: str = "unknown"
    candidate_since_ms: int | None = None
    last_timestamp_ms: int | None = None


class NightPositionEngine:
    """Classify recumbent orientation from the normalized gravity vector.

    The default axis mapping follows the mounting already emulated by the
    project simulator. Its signs must be confirmed once against the physical
    shirt before clinical interpretation.
    """

    CLASSIFIER_VERSION = 1
    POSITIONS = ("supine", "prone", "right_side", "left_side", "unknown")

    def __init__(
        self,
        *,
        session_provider: SessionProvider,
        summary_updater: SummaryUpdater,
        persister: PositionPersister,
        ema_alpha: float = 0.35,
        enter_threshold: float = 0.75,
        exit_threshold: float = 0.65,
        persistence_seconds: float = 2.0,
        gap_seconds: float = 10.0,
    ) -> None:
        self._session_provider = session_provider
        self._summary_updater = summary_updater
        self._persister = persister
        self._ema_alpha = ema_alpha
        self._enter_threshold = enter_threshold
        self._exit_threshold = exit_threshold
        self._persistence_ms = round(persistence_seconds * 1000)
        self._gap_seconds = gap_seconds
        self._states: dict[str, NightState] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _normalized_vector(sample: dict[str, Any]) -> tuple[float, float, float] | None:
        x, y, z = float(sample["x"]), float(sample["y"]), float(sample["z"])
        magnitude = math.sqrt(x * x + y * y + z * z)
        if magnitude <= 0:
            return None
        return x / magnitude, y / magnitude, z / magnitude

    @staticmethod
    def _component(position: str, x: float, z: float) -> float:
        return {
            "supine": z,
            "prone": -z,
            "right_side": x,
            "left_side": -x,
        }.get(position, -1.0)

    def _instant_position(self, state: NightState, x: float, z: float) -> tuple[str, float]:
        if (
            state.position != "unknown"
            and self._component(state.position, x, z) >= self._exit_threshold
        ):
            return state.position, self._component(state.position, x, z)
        candidates = {
            "supine": z,
            "prone": -z,
            "right_side": x,
            "left_side": -x,
        }
        position, confidence = max(candidates.items(), key=lambda item: item[1])
        return (position, confidence) if confidence >= self._enter_threshold else ("unknown", confidence)

    def process(self, sample: dict[str, Any]) -> dict[str, Any] | None:
        device_id = str(sample["device_id"])
        patient_code = str(sample["patient_id"])
        session = self._session_provider(device_id, patient_code)
        if session is None:
            return None
        vector = self._normalized_vector(sample)
        if vector is None:
            return None
        timestamp_ms = int(sample["timestamp"])
        with self._lock:
            state = self._states.setdefault(str(session["id"]), NightState())
            x, y, z = vector
            if state.filtered_x is None:
                state.filtered_x, state.filtered_y, state.filtered_z = x, y, z
            else:
                alpha = self._ema_alpha
                state.filtered_x = alpha * x + (1 - alpha) * state.filtered_x
                state.filtered_y = alpha * y + (1 - alpha) * state.filtered_y
                state.filtered_z = alpha * z + (1 - alpha) * state.filtered_z
                filtered_magnitude = math.sqrt(
                    state.filtered_x**2 + state.filtered_y**2 + state.filtered_z**2
                )
                if filtered_magnitude:
                    state.filtered_x /= filtered_magnitude
                    state.filtered_y /= filtered_magnitude
                    state.filtered_z /= filtered_magnitude

            previous_position = state.position
            elapsed_seconds = 0.0
            data_gap_seconds = 0.0
            if state.last_timestamp_ms is not None:
                elapsed_seconds = max(0.0, (timestamp_ms - state.last_timestamp_ms) / 1000)
                if elapsed_seconds > self._gap_seconds:
                    data_gap_seconds = elapsed_seconds
                    elapsed_seconds = 0.0

            instant, confidence = self._instant_position(
                state, state.filtered_x, state.filtered_z
            )
            if instant != state.candidate:
                state.candidate = instant
                state.candidate_since_ms = timestamp_ms
            elif (
                instant != state.position
                and state.candidate_since_ms is not None
                and timestamp_ms - state.candidate_since_ms >= self._persistence_ms
            ):
                state.position = instant

            changed = state.position != previous_position
            state.last_timestamp_ms = timestamp_ms
            if data_gap_seconds:
                self._summary_updater(str(session["id"]), "data_gap", data_gap_seconds, False)
            if elapsed_seconds:
                self._summary_updater(
                    str(session["id"]), previous_position, elapsed_seconds, changed
                )

            result = {
                "timestamp": timestamp_ms,
                "session_id": session["id"],
                "patient_id": patient_code,
                "device_id": device_id,
                "position": state.position,
                "candidate_position": instant,
                "confidence": round(max(0.0, min(1.0, confidence)), 3),
                "classifier_version": self.CLASSIFIER_VERSION,
                "x": round(state.filtered_x, 4),
                "y": round(state.filtered_y, 4),
                "z": round(state.filtered_z, 4),
                "data_gap_seconds": round(data_gap_seconds, 3),
            }
            self._persister(result)
            return result
