import unittest
import os
import sqlite3
import json
from datetime import datetime
from fastapi import HTTPException

# Add backend directory to path if needed (though running with python -m unittest will handle it)
import sys
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from alarm_system import FloodAlarmSystem
from main import AnalyzeRequest, validate_analyze_request


class TestFloodAlarmSystem(unittest.TestCase):
    def setUp(self):
        # Initialize the alarm system with a temporary directory
        self.test_data_dir = os.path.join(backend_dir, 'test_data')
        self.alarm_system = FloodAlarmSystem(data_dir=self.test_data_dir)
        # Override db path to a dedicated test database file
        self.test_db_path = os.path.join(self.test_data_dir, 'test_floodwatch.db')
        self.alarm_system.db_path = self.test_db_path
        self.alarm_system._init_db()

    def tearDown(self):
        # Clean up database and test directory
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except Exception:
                pass
        if os.path.exists(self.test_data_dir):
            try:
                import shutil
                shutil.rmtree(self.test_data_dir)
            except Exception:
                pass

    def test_severity_classification(self):
        self.assertEqual(self.alarm_system._classify(0.5), 'NONE')
        self.assertEqual(self.alarm_system._classify(5.0), 'LOW')
        self.assertEqual(self.alarm_system._classify(25.0), 'MEDIUM')
        self.assertEqual(self.alarm_system._classify(75.0), 'HIGH')
        self.assertEqual(self.alarm_system._classify(150.0), 'CRITICAL')

    def test_get_actions(self):
        actions_none = self.alarm_system._get_actions('NONE')
        self.assertIn('Continue routine monitoring', actions_none)

        actions_critical = self.alarm_system._get_actions('CRITICAL')
        self.assertIn('IMMEDIATE EVACUATION of all flood-prone areas', actions_critical)

    def test_subscriber_crud(self):
        # Subscribe a user
        res = self.alarm_system.subscribe("test@example.com", "Test User", ["Mumbai"])
        self.assertEqual(res['status'], 'subscribed')

        # Retrieve active subscribers
        subs = self.alarm_system.get_subscribers()
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]['email'], "test@example.com")
        self.assertEqual(subs[0]['name'], "Test User")
        self.assertEqual(subs[0]['cities'], ["Mumbai"])

        # Update subscriber
        res_update = self.alarm_system.subscribe("test@example.com", "Test User Updated", ["Mumbai", "Chennai"])
        self.assertEqual(res_update['status'], 'updated')

        subs = self.alarm_system.get_subscribers()
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]['name'], "Test User Updated")
        self.assertEqual(subs[0]['cities'], ["Mumbai", "Chennai"])

        # Unsubscribe
        res_unsub = self.alarm_system.unsubscribe("test@example.com")
        self.assertEqual(res_unsub['status'], 'unsubscribed')

        subs = self.alarm_system.get_subscribers()
        self.assertEqual(len(subs), 0)

    def test_alarm_evaluation_and_history(self):
        # Create a mock analysis results dict
        mock_results = {
            'location_name': 'Mumbai',
            'coordinates': {'lat': 19.0760, 'lon': 72.8777},
            'new_flooded_area': 12.5,
            'water_before': 100.0,
            'water_after': 112.5,
            'water_coverage_change': 12.5,
            'start_date': '01-07-2026',
            'end_date': '07-07-2026'
        }

        # Evaluate and save alarm
        alarm = self.alarm_system.evaluate(mock_results)
        self.assertEqual(alarm['severity'], 'MEDIUM')
        self.assertEqual(alarm['location_name'], 'Mumbai')
        self.assertEqual(alarm['metrics']['new_flooded_area_km2'], 12.5)

        # Get latest alarm
        latest = self.alarm_system.get_latest_alarm()
        self.assertIsNotNone(latest)
        self.assertEqual(latest['alarm_id'], alarm['alarm_id'])

        # Get alarm history
        history = self.alarm_system.get_alarm_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['alarm_id'], alarm['alarm_id'])


class TestInputValidation(unittest.TestCase):
    def test_valid_request(self):
        req = AnalyzeRequest(
            location="Mumbai",
            before_start_date="01-01-2026",
            before_end_date="05-01-2026",
            after_start_date="10-01-2026",
            after_end_date="15-01-2026",
            lat=19.0760,
            lon=72.8777
        )
        # Should execute without raising HTTP exceptions
        try:
            validate_analyze_request(req)
        except HTTPException as e:
            self.fail(f"validate_analyze_request raised HTTPException unexpectedly: {e.detail}")

    def test_invalid_date_format(self):
        req = AnalyzeRequest(
            location="Mumbai",
            before_start_date="01/01/2026",  # Invalid separator
            before_end_date="05-01-2026",
            after_start_date="10-01-2026",
            after_end_date="15-01-2026"
        )
        with self.assertRaises(HTTPException) as ctx:
            validate_analyze_request(req)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Invalid date format", ctx.exception.detail)

    def test_date_chronology_before_after(self):
        req = AnalyzeRequest(
            location="Mumbai",
            before_start_date="05-01-2026",
            before_end_date="01-01-2026",  # End is before start
            after_start_date="10-01-2026",
            after_end_date="15-01-2026"
        )
        with self.assertRaises(HTTPException) as ctx:
            validate_analyze_request(req)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Before start date must be before or equal to before end date", ctx.exception.detail)

    def test_baseline_overlap(self):
        req = AnalyzeRequest(
            location="Mumbai",
            before_start_date="01-01-2026",
            before_end_date="10-01-2026",
            after_start_date="08-01-2026",  # Overlaps / starts before baseline ends
            after_end_date="15-01-2026"
        )
        with self.assertRaises(HTTPException) as ctx:
            validate_analyze_request(req)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Baseline period (before) must end before the current period", ctx.exception.detail)

    def test_invalid_coordinates(self):
        req = AnalyzeRequest(
            location="Mumbai",
            before_start_date="01-01-2026",
            before_end_date="05-01-2026",
            after_start_date="10-01-2026",
            after_end_date="15-01-2026",
            lat=120.0,  # Invalid latitude (>90)
            lon=72.8777
        )
        with self.assertRaises(HTTPException) as ctx:
            validate_analyze_request(req)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Latitude must be between -90 and 90", ctx.exception.detail)

    def test_unrecognized_custom_location_without_coordinates(self):
        req = AnalyzeRequest(
            location="Atlantis",  # Unknown city
            before_start_date="01-01-2026",
            before_end_date="05-01-2026",
            after_start_date="10-01-2026",
            after_end_date="15-01-2026"
        )
        with self.assertRaises(HTTPException) as ctx:
            validate_analyze_request(req)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("is not a recognized city", ctx.exception.detail)


if __name__ == '__main__':
    unittest.main()
