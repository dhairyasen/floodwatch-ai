import json
import os
import sqlite3
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
        
        self.db_path = os.path.join(os.path.dirname(self.data_dir), 'floodwatch.db')
        self._init_db()
        self._migrate_legacy_data()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Create alarms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alarms (
                alarm_id TEXT PRIMARY KEY,
                timestamp TEXT,
                location_name TEXT,
                lat REAL,
                lon REAL,
                severity TEXT,
                severity_color TEXT,
                severity_icon TEXT,
                message TEXT,
                new_flooded_area_km2 REAL,
                water_before_km2 REAL,
                water_after_km2 REAL,
                water_coverage_change_pct REAL,
                recommended_actions TEXT,
                analysis_period_start TEXT,
                analysis_period_end TEXT
            )
        ''')
        # Create subscribers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                email TEXT PRIMARY KEY,
                name TEXT,
                cities TEXT,
                subscribed_at TEXT,
                active INTEGER DEFAULT 1
            )
        ''')
        conn.commit()
        conn.close()

    def _migrate_legacy_data(self):
        # 1. Migrate subscribers
        if os.path.exists(self.subscribers_file):
            try:
                with open(self.subscribers_file) as f:
                    subs = json.load(f)
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                for s in subs:
                    if 'email' in s:
                        cursor.execute('''
                            INSERT OR IGNORE INTO subscribers (email, name, cities, subscribed_at, active)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            s['email'].lower(),
                            s.get('name', ''),
                            json.dumps(s.get('cities', [])),
                            s.get('subscribed_at', datetime.now().isoformat()),
                            1 if s.get('active', True) else 0
                        ))
                conn.commit()
                conn.close()
                os.rename(self.subscribers_file, self.subscribers_file + ".bak")
                print("[OK] Migrated subscribers to SQLite.")
            except Exception as e:
                print(f"[WARNING] Failed to migrate legacy subscribers: {e}")

        # 2. Migrate alarms
        if os.path.exists(self.data_dir):
            alarm_files = [f for f in os.listdir(self.data_dir) if f.endswith('.json') and f.startswith('alarm_')]
            if alarm_files:
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    for fname in alarm_files:
                        fpath = os.path.join(self.data_dir, fname)
                        with open(fpath) as f:
                            a = json.load(f)
                        if 'alarm_id' in a:
                            cursor.execute('''
                                INSERT OR IGNORE INTO alarms (
                                    alarm_id, timestamp, location_name, lat, lon, severity,
                                    severity_color, severity_icon, message, new_flooded_area_km2,
                                    water_before_km2, water_after_km2, water_coverage_change_pct,
                                    recommended_actions, analysis_period_start, analysis_period_end
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                a['alarm_id'],
                                a['timestamp'],
                                a['location_name'],
                                a['coordinates'].get('lat'),
                                a['coordinates'].get('lon'),
                                a['severity'],
                                a['severity_color'],
                                a['severity_icon'],
                                a['message'],
                                a['metrics'].get('new_flooded_area_km2', 0.0),
                                a['metrics'].get('water_before_km2', 0.0),
                                a['metrics'].get('water_after_km2', 0.0),
                                a['metrics'].get('water_coverage_change_pct', 0.0),
                                json.dumps(a.get('recommended_actions', [])),
                                a['analysis_period'].get('start', ''),
                                a['analysis_period'].get('end', '')
                            ))
                    conn.commit()
                    conn.close()
                    
                    bak_dir = os.path.join(self.data_dir, 'legacy_backup')
                    os.makedirs(bak_dir, exist_ok=True)
                    for fname in alarm_files:
                        try:
                            os.rename(os.path.join(self.data_dir, fname), os.path.join(bak_dir, fname))
                        except Exception:
                            pass
                    print("[OK] Migrated alarms to SQLite.")
                except Exception as e:
                    print(f"[WARNING] Failed to migrate legacy alarms: {e}")

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO alarms (
                alarm_id, timestamp, location_name, lat, lon, severity,
                severity_color, severity_icon, message, new_flooded_area_km2,
                water_before_km2, water_after_km2, water_coverage_change_pct,
                recommended_actions, analysis_period_start, analysis_period_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            alarm['alarm_id'],
            alarm['timestamp'],
            alarm['location_name'],
            alarm['coordinates'].get('lat'),
            alarm['coordinates'].get('lon'),
            alarm['severity'],
            alarm['severity_color'],
            alarm['severity_icon'],
            alarm['message'],
            alarm['metrics'].get('new_flooded_area_km2', 0.0),
            alarm['metrics'].get('water_before_km2', 0.0),
            alarm['metrics'].get('water_after_km2', 0.0),
            alarm['metrics'].get('water_coverage_change_pct', 0.0),
            json.dumps(alarm.get('recommended_actions', [])),
            alarm['analysis_period'].get('start', ''),
            alarm['analysis_period'].get('end', '')
        ))
        conn.commit()
        conn.close()

    def get_alarm_history(self, limit: int = 20) -> list:
        """Return the most recent `limit` alarm records, newest first."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT alarm_id, timestamp, location_name, lat, lon, severity,
                   severity_color, severity_icon, message, new_flooded_area_km2,
                   water_before_km2, water_after_km2, water_coverage_change_pct,
                   recommended_actions, analysis_period_start, analysis_period_end
            FROM alarms
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                'alarm_id': r[0],
                'timestamp': r[1],
                'location_name': r[2],
                'coordinates': {'lat': r[3], 'lon': r[4]},
                'severity': r[5],
                'severity_color': r[6],
                'severity_icon': r[7],
                'message': r[8],
                'metrics': {
                    'new_flooded_area_km2': r[9],
                    'water_before_km2': r[10],
                    'water_after_km2': r[11],
                    'water_coverage_change_pct': r[12]
                },
                'recommended_actions': json.loads(r[13]) if r[13] else [],
                'analysis_period': {
                    'start': r[14],
                    'end': r[15]
                }
            })
        return history

    def get_latest_alarm(self) -> Optional[dict]:
        history = self.get_alarm_history(limit=1)
        return history[0] if history else None

    # ------------------------------------------------------------------ #
    # Subscriber management
    # ------------------------------------------------------------------ #
    def subscribe(self, email: str, name: str = '', cities: list = None) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        email_lower = email.lower()
        
        cursor.execute('SELECT email, name, cities FROM subscribers WHERE email = ?', (email_lower,))
        existing = cursor.fetchone()
        
        if existing:
            db_name = existing[1]
            db_cities_json = existing[2]
            
            new_name = name or db_name or ''
            new_cities = cities if cities is not None else (json.loads(db_cities_json) if db_cities_json else [])
            
            cursor.execute('''
                UPDATE subscribers
                SET name = ?, cities = ?, active = 1
                WHERE email = ?
            ''', (new_name, json.dumps(new_cities), email_lower))
            conn.commit()
            conn.close()
            return {'status': 'updated', 'email': email}
        else:
            cursor.execute('''
                INSERT INTO subscribers (email, name, cities, subscribed_at, active)
                VALUES (?, ?, ?, ?, 1)
            ''', (
                email_lower,
                name,
                json.dumps(cities or []),
                datetime.now().isoformat(),
            ))
            conn.commit()
            conn.close()
            return {'status': 'subscribed', 'email': email}

    def unsubscribe(self, email: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM subscribers WHERE email = ?', (email.lower(),))
        conn.commit()
        conn.close()
        return {'status': 'unsubscribed', 'email': email}

    def get_subscribers(self) -> list:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT email, name, cities, subscribed_at, active FROM subscribers WHERE active = 1')
        rows = cursor.fetchall()
        conn.close()
        
        subs = []
        for r in rows:
            subs.append({
                'email': r[0],
                'name': r[1],
                'cities': json.loads(r[2]) if r[2] else [],
                'subscribed_at': r[3],
                'active': bool(r[4])
            })
        return subs