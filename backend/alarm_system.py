"""
FloodWatch AI - Automated Flood Alarm System (Phase 2)
Threshold-based flood detection alerts with severity classification
"""

import json
import os
from datetime import datetime
from typing import Optional

# Severity thresholds (new_flooded_area in km²)
ALARM_THRESHOLDS = {
    'NONE':     (0,    1.0),
    'LOW':      (1.0,  10.0),
    'MEDIUM':   (10.0, 50.0),
    'HIGH':     (50.0, 100.0),
    'CRITICAL': (100.0, float('inf')),
}

ALARM_COLORS = {
    'NONE':     '#10b981',
    'LOW':      '#f59e0b',
    'MEDIUM':   '#f97316',
    'HIGH':     '#ef4444',
    'CRITICAL': '#dc2626',
}

ALARM_ICONS = {
    'NONE':     '✅',
    'LOW':      '🟡',
    'MEDIUM':   '🟠',
    'HIGH':     '🔴',
    'CRITICAL': '🚨',
}

ALARM_MESSAGES = {
    'NONE':     'No significant flooding detected. Conditions appear normal.',
    'LOW':      'Minor flooding detected. Monitor situation closely.',
    'MEDIUM':   'Moderate flooding detected. Prepare for possible evacuation in low-lying areas.',
    'HIGH':     'Severe flooding detected. Immediate action recommended. Alert local authorities.',
    'CRITICAL': 'CRITICAL FLOOD EVENT. Evacuate immediately. Contact disaster management teams.',
}


class FloodAlarmSystem:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            # Default: project_root/data/alarms/
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base, 'data', 'alarms')
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.subscribers_file = os.path.join(
            os.path.dirname(self.data_dir), 'subscribers.json'
        )
        os.makedirs(os.path.dirname(self.subscribers_file), exist_ok=True)

    # ------------------------------------------------------------------ #
    # Core alarm evaluation
    # ------------------------------------------------------------------ #
    def evaluate(self, analysis_results: dict) -> dict:
        """
        Given a FloodAnalyzer results dict, compute and persist an alarm record.
        Returns the alarm dict (safe to return as JSON from FastAPI).
        """
        new_flood = analysis_results.get('new_flooded_area', 0.0)
        change_pct = analysis_results.get('water_coverage_change', 0.0)
        location_name = analysis_results.get('location_name', 'Unknown')
        coords = analysis_results.get('coordinates', {})

        severity = self._classify(new_flood)
        alarm = {
            'alarm_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'timestamp': datetime.now().isoformat(),
            'location_name': location_name,
            'coordinates': coords,
            'severity': severity,
            'severity_color': ALARM_COLORS[severity],
            'severity_icon': ALARM_ICONS[severity],
            'message': ALARM_MESSAGES[severity],
            'metrics': {
                'new_flooded_area_km2': new_flood,
                'water_before_km2': analysis_results.get('water_before', 0.0),
                'water_after_km2': analysis_results.get('water_after', 0.0),
                'water_coverage_change_pct': change_pct,
            },
            'recommended_actions': self._get_actions(severity),
            'analysis_period': {
                'start': analysis_results.get('start_date', ''),
                'end': analysis_results.get('end_date', ''),
            },
        }

        # Persist
        self._save_alarm(alarm)
        return alarm

    def _classify(self, new_flood_km2: float) -> str:
        for level, (lo, hi) in ALARM_THRESHOLDS.items():
            if lo <= new_flood_km2 < hi:
                return level
        return 'CRITICAL'

    def _get_actions(self, severity: str) -> list:
        actions = {
            'NONE': [
                'Continue routine monitoring',
                'Check back after next rain event',
            ],
            'LOW': [
                'Monitor water levels hourly',
                'Alert local municipal body',
                'Avoid flood-prone low-lying zones',
            ],
            'MEDIUM': [
                'Issue advisory to residents in low-lying areas',
                'Pre-position relief materials',
                'Activate district emergency response team',
                'Monitor rainfall forecasts closely',
            ],
            'HIGH': [
                'Initiate evacuation of vulnerable zones immediately',
                'Alert State Disaster Response Force (SDRF)',
                'Open relief camps',
                'Deploy rescue teams and boats',
                'Establish emergency helpline',
            ],
            'CRITICAL': [
                'IMMEDIATE EVACUATION of all flood-prone areas',
                'Deploy NDRF and Army rescue units',
                'Activate National Crisis Management Committee',
                'Issue public broadcast warnings',
                'Open all emergency shelters',
                'Request aerial rescue support if required',
            ],
        }
        return actions.get(severity, [])

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def _save_alarm(self, alarm: dict):
        fname = f"alarm_{alarm['alarm_id']}.json"
        path = os.path.join(self.data_dir, fname)
        with open(path, 'w') as f:
            json.dump(alarm, f, indent=2)

    def get_alarm_history(self, limit: int = 20) -> list:
        """Return the most recent `limit` alarm records, newest first."""
        files = sorted(
            [f for f in os.listdir(self.data_dir) if f.endswith('.json')],
            reverse=True
        )
        history = []
        for fname in files[:limit]:
            try:
                with open(os.path.join(self.data_dir, fname)) as f:
                    history.append(json.load(f))
            except Exception:
                pass
        return history

    def get_latest_alarm(self) -> Optional[dict]:
        history = self.get_alarm_history(limit=1)
        return history[0] if history else None

    # ------------------------------------------------------------------ #
    # Subscriber management
    # ------------------------------------------------------------------ #
    def _load_subscribers(self) -> list:
        if not os.path.exists(self.subscribers_file):
            return []
        try:
            with open(self.subscribers_file) as f:
                return json.load(f)
        except Exception:
            return []

    def _save_subscribers(self, subs: list):
        with open(self.subscribers_file, 'w') as f:
            json.dump(subs, f, indent=2)

    def subscribe(self, email: str, name: str = '', cities: list = None) -> dict:
        subs = self._load_subscribers()
        existing = next((s for s in subs if s['email'] == email.lower()), None)
        if existing:
            existing['cities'] = cities or existing.get('cities', [])
            existing['name'] = name or existing.get('name', '')
            self._save_subscribers(subs)
            return {'status': 'updated', 'email': email}
        subs.append({
            'email': email.lower(),
            'name': name,
            'cities': cities or [],
            'subscribed_at': datetime.now().isoformat(),
            'active': True,
        })
        self._save_subscribers(subs)
        return {'status': 'subscribed', 'email': email}

    def unsubscribe(self, email: str) -> dict:
        subs = self._load_subscribers()
        subs = [s for s in subs if s['email'] != email.lower()]
        self._save_subscribers(subs)
        return {'status': 'unsubscribed', 'email': email}

    def get_subscribers(self) -> list:
        return [s for s in self._load_subscribers() if s.get('active', True)]