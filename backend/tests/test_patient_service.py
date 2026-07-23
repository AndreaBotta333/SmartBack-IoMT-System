import unittest
from unittest.mock import Mock

from app.services.patient_service import (
    PatientAlreadyAssociated,
    PatientAssignedToAnotherDoctor,
    PatientNotRegistered,
    PatientService,
)


class PatientServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.service = PatientService(
            self.repository,
            messaging=None,
            password_hasher=lambda _password: ("digest", "salt"),
        )

    def test_associate_existing_requires_known_patient(self):
        self.repository.by_fiscal_code.return_value = None
        with self.assertRaises(PatientNotRegistered):
            self.service.associate_existing("doctor-1", "RSSMRA00A00H000A")

    def test_associate_existing_enforces_single_doctor(self):
        patient = {"id": "patient-1"}
        self.repository.by_fiscal_code.return_value = patient
        self.repository.doctor_links.return_value = [{"doctor_id": "doctor-2"}]
        with self.assertRaises(PatientAssignedToAnotherDoctor):
            self.service.associate_existing("doctor-1", "RSSMRA00A00H000A")

        self.repository.doctor_links.return_value = [{"doctor_id": "doctor-1"}]
        with self.assertRaises(PatientAlreadyAssociated):
            self.service.associate_existing("doctor-1", "RSSMRA00A00H000A")

    def test_monitoring_configuration_is_delegated_to_repository(self):
        self.service.save_monitoring_config(
            patient_id="patient-1",
            updated_by="doctor-1",
            moderate_deviation_deg=10.0,
            marked_deviation_deg=20.0,
            moderate_roll_deg=8.0,
            marked_roll_deg=16.0,
            persistence_seconds=5.0,
        )
        self.repository.save_monitoring_config.assert_called_once_with(
            patient_id="patient-1",
            updated_by="doctor-1",
            moderate_deviation_deg=10.0,
            marked_deviation_deg=20.0,
            moderate_roll_deg=8.0,
            marked_roll_deg=16.0,
            persistence_seconds=5.0,
        )

        self.service.reset_monitoring_config("patient-1")
        self.repository.delete_monitoring_config.assert_called_once_with(
            "patient-1"
        )


if __name__ == "__main__":
    unittest.main()
