"""
FloodWatch AI - Weekly Email Report Generator (Phase 2)
Builds HTML reports from alarm history and sends via smtplib / Gmail SMTP.

Environment variables expected:
    EMAIL_SENDER      - Gmail address used to send reports
    EMAIL_PASSWORD    - App password (NOT account password) for Gmail SMTP
    EMAIL_RECIPIENTS  - Comma-separated fallback recipients (used if no subscribers in DB)
"""

import os
import json
import smtplib
import logging
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import List, Optional

from alarm_system import FloodAlarmSystem, ALARM_COLORS, ALARM_ICONS

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Weather Forecast Helper
# ------------------------------------------------------------------ #
def get_weather_desc(code):
    if code == 0:
        return "Clear Sky ☀️"
    elif code in (1, 2, 3):
        return "Partly Cloudy 🌤️"
    elif code in (45, 48):
        return "Foggy 🌫️"
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return "Rainy 🌧️"
    elif code in (71, 73, 75):
        return "Snowy ❄️"
    elif code in (95, 96, 99):
        return "Thunderstorm ⛈️"
    return "Variable 🌤️"


def resolve_coordinates(city_name: str):
    from config import CITY_COORDINATES
    city_lower = str(city_name).lower().strip()
    if city_lower in CITY_COORDINATES:
        return CITY_COORDINATES[city_lower]['lat'], CITY_COORDINATES[city_lower]['lon']
    
    # Try parsing as lat, lon string
    try:
        parts = city_name.split(',')
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except:
        pass
        
    # Try simple Nominatim lookup
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={city_name}&format=json&limit=1"
        headers = {'User-Agent': 'FloodWatch-AI/1.0'}
        res = requests.get(url, headers=headers, timeout=3.0)
        data = res.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        logger.warning(f"Failed to geocode '{city_name}' for weather: {e}")
        
    return None


def _get_weather_forecast_html(cities: list) -> str:
    if not cities:
        cities = ['Chennai', 'Mumbai']
        
    resolved_cities = []
    for c in cities:
        if c.lower() == 'all':
            resolved_cities.extend(['Chennai', 'Mumbai'])
        else:
            resolved_cities.append(c)
            
    unique_cities = []
    for c in resolved_cities:
        c_title = str(c).strip().title()
        if c_title not in unique_cities:
            unique_cities.append(c_title)
            
    unique_cities = unique_cities[:4]
    
    rows = []
    for city in unique_cities:
        coords = resolve_coordinates(city)
        if not coords:
            continue
        lat, lon = coords
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=precipitation_sum,weather_code&timezone=auto"
            res = requests.get(url, timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                daily = data.get('daily', {})
                precip = sum(daily.get('precipitation_sum', [0.0]))
                codes = daily.get('weather_code', [0])
                code = codes[0] if codes else 0
                desc = get_weather_desc(code)
                
                if precip >= 100.0:
                    risk = '<span style="color:#ef4444; font-weight:700;">⚠️ High Risk</span>'
                elif precip >= 40.0:
                    risk = '<span style="color:#f59e0b; font-weight:700;">🌧️ Medium Risk</span>'
                else:
                    risk = '<span style="color:#22c55e; font-weight:700;">☀️ Low Risk</span>'
                    
                rows.append(f"""
              <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:10px 0; color:#1e293b; font-weight:600;">{city}</td>
                <td style="padding:10px 0; text-align:center; color:#475569;">{desc}</td>
                <td style="padding:10px 0; text-align:right; color:#1e293b; font-weight:600;">{precip:.1f} mm</td>
                <td style="padding:10px 0; text-align:right;">{risk}</td>
              </tr>""")
        except Exception as e:
            logger.warning(f"Failed to fetch weather for {city}: {e}")
            
    if not rows:
        return ""
        
    rows_str = "\n".join(rows)
    return f"""
  <!-- Weather Forecast Section -->
  <tr>
    <td style="padding:24px 40px 0;">
      <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:20px;">
        <p style="margin:0 0 12px; font-size:12px; color:#64748b; font-weight:600;
                  text-transform:uppercase; letter-spacing:0.5px;">🔮 Next Week Prediction: Rainfall & Flood Risk</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px; border-collapse:collapse;">
          <thead>
            <tr style="border-bottom:2px solid #e2e8f0;">
              <th style="padding:6px 0; text-align:left; color:#64748b; font-weight:600;">Location</th>
              <th style="padding:6px 0; text-align:center; color:#64748b; font-weight:600;">Forecast</th>
              <th style="padding:6px 0; text-align:right; color:#64748b; font-weight:600;">7-Day Rain</th>
              <th style="padding:6px 0; text-align:right; color:#64748b; font-weight:600;">Flood Risk</th>
            </tr>
          </thead>
          <tbody>
            {rows_str}
          </tbody>
        </table>
      </div>
    </td>
  </tr>"""


# ------------------------------------------------------------------ #
# HTML report builder
# ------------------------------------------------------------------ #
def build_html_report(alarm_history: list, week_start: str, week_end: str, cities: list = None) -> str:
    """Render a full HTML email from a list of alarm dicts."""
    # Format cities string for header
    if cities:
        cleaned_cities = [str(c).strip().title() for c in cities if str(c).lower() != 'all']
        if cleaned_cities:
            cities_str = ", ".join(cleaned_cities)
        else:
            cities_str = "All Monitored Cities"
    else:
        cities_str = "All Monitored Cities"

    try:
        weather_block = _get_weather_forecast_html(cities)
    except Exception as e:
        logger.warning(f"Failed to build weather forecast block: {e}")
        weather_block = ""

    # Summary counts
    counts = {'NONE': 0, 'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
    for a in alarm_history:
        sev = a.get('severity', 'NONE')
        counts[sev] = counts.get(sev, 0) + 1

    total = len(alarm_history)
    worst = _worst_severity(alarm_history)
    worst_color = ALARM_COLORS.get(worst, '#64748b')
    worst_icon = ALARM_ICONS.get(worst, '✅')

    # Build alarm rows or safety banner
    if not alarm_history:
        events_block = '''
      <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; padding:24px; text-align:center;">
        <div style="font-size:32px; margin-bottom:8px;">🛡️</div>
        <h3 style="margin:0 0 6px; color:#166534; font-size:16px; font-weight:700;">All Monitored Locations are Stable</h3>
        <p style="margin:0; font-size:13px; color:#16a34a; line-height:1.5;">
          No active flood alerts or abnormal surface water expansions were detected for your monitored cities during this period.
        </p>
      </div>'''
    else:
        rows_html = ''
        for a in alarm_history[:30]:   # cap at 30 rows
            sev = a.get('severity', 'NONE')
            color = ALARM_COLORS.get(sev, '#64748b')
            icon = ALARM_ICONS.get(sev, '')
            ts = a.get('timestamp', '')[:16].replace('T', ' ')
            loc = a.get('location_name', 'Unknown')
            flood_km2 = a.get('metrics', {}).get('new_flooded_area_km2', 0)
            change = a.get('metrics', {}).get('water_coverage_change_pct', 0)
            rows_html += f'''
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px 14px; color:#1e293b;">{ts}</td>
                <td style="padding:10px 14px; color:#1e293b;">{loc}</td>
                <td style="padding:10px 14px; text-align:center;">
                    <span style="background:{color}22; color:{color}; font-weight:700;
                                 padding:3px 10px; border-radius:20px; font-size:12px;">
                        {icon} {sev}
                    </span>
                </td>
                <td style="padding:10px 14px; text-align:right; color:#1e293b;">{flood_km2:.2f} km²</td>
                <td style="padding:10px 14px; text-align:right; color:#1e293b;">{change:+.1f}%</td>
            </tr>'''

        events_block = f'''
      <p style="margin:0 0 12px; font-size:15px; font-weight:700; color:#1e293b;">
        📋 Flood Events Log
      </p>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse; border:1px solid #e2e8f0; border-radius:8px;
                    overflow:hidden; font-size:13px;">
        <thead>
          <tr style="background:#f8fafc;">
            <th style="padding:10px 14px; text-align:left; color:#64748b;
                       font-weight:600; border-bottom:2px solid #e2e8f0;">Time</th>
            <th style="padding:10px 14px; text-align:left; color:#64748b;
                       font-weight:600; border-bottom:2px solid #e2e8f0;">Location</th>
            <th style="padding:10px 14px; text-align:center; color:#64748b;
                       font-weight:600; border-bottom:2px solid #e2e8f0;">Severity</th>
            <th style="padding:10px 14px; text-align:right; color:#64748b;
                       font-weight:600; border-bottom:2px solid #e2e8f0;">New Flood</th>
            <th style="padding:10px 14px; text-align:right; color:#64748b;
                       font-weight:600; border-bottom:2px solid #e2e8f0;">Change</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>'''

    # Summary pill HTML
    pills = ''
    pill_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE']
    for sev in pill_order:
        if counts[sev] > 0:
            c = ALARM_COLORS[sev]
            pills += f'''
            <div style="display:inline-block; margin:4px; background:{c}22;
                        border:1px solid {c}; border-radius:20px;
                        padding:5px 14px; font-size:13px; color:{c}; font-weight:600;">
                {ALARM_ICONS[sev]} {sev}: {counts[sev]}
            </div>'''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FloodWatch AI — Weekly Report</title>
</head>
<body style="margin:0; padding:0; background:#f0f4f8; font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8; padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0"
       style="background:#ffffff; border-radius:16px; overflow:hidden;
              box-shadow:0 8px 24px rgba(0,0,0,0.12); max-width:640px; width:100%;">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,#0052a3,#00b3b3);
               padding:36px 40px; text-align:center;">
      <div style="font-size:36px; margin-bottom:6px;">🌊</div>
      <h1 style="color:#ffffff; margin:0; font-size:26px; font-weight:700;
                 letter-spacing:-0.5px;">FloodWatch AI</h1>
      <p style="color:#b3d9ff; margin:6px 0 0; font-size:14px;">
        Weekly Flood Monitoring Report
      </p>
      <p style="color:#e0f2ff; margin:8px 0 0; font-size:12px;">
        {week_start} &nbsp;→&nbsp; {week_end}
      </p>
      <p style="color:#ffffff; margin:8px 0 0; font-size:13px; font-weight:600;">
        📍 Monitored: {cities_str}
      </p>
    </td>
  </tr>

  <!-- Overall status banner -->
  <tr>
    <td style="padding:24px 40px 0;">
      <div style="background:{worst_color}15; border-left:4px solid {worst_color};
                  border-radius:8px; padding:16px 20px;">
        <p style="margin:0; font-size:18px; font-weight:700; color:{worst_color};">
          {worst_icon} Worst Severity This Week: {worst}
        </p>
        <p style="margin:6px 0 0; font-size:13px; color:#64748b;">
          {total} analysis event{'s' if total != 1 else ''} processed this week.
        </p>
      </div>
    </td>
  </tr>

  <!-- Summary pills -->
  <tr>
    <td style="padding:20px 40px 0;">
      <p style="margin:0 0 8px; font-size:12px; color:#64748b; font-weight:600;
                text-transform:uppercase; letter-spacing:0.5px;">Event Breakdown</p>
      {pills if pills else '<p style="color:#64748b; font-size:13px; margin:0;">No events this week</p>'}
    </td>
  </tr>

  {weather_block}

  <!-- Events table -->
  <tr>
    <td style="padding:28px 40px 0;">
      {events_block}
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:32px 40px;">
      <hr style="border:none; border-top:1px solid #e2e8f0; margin:0 0 20px;">
      <p style="margin:0; font-size:12px; color:#94a3b8; text-align:center; line-height:1.8;">
        🛰️ Data source: Sentinel-2 (10m resolution) via Google Earth Engine<br>
        📍 FloodWatch AI — India Flood Monitoring System<br>
        Generated automatically on {(datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d %b %Y at %H:%M IST')}
      </p>
      <p style="margin:12px 0 0; font-size:11px; color:#cbd5e1; text-align:center;">
        To unsubscribe, visit your FloodWatch AI dashboard settings.
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


def _worst_severity(alarm_history: list) -> str:
    order = ['NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    worst = 'NONE'
    for a in alarm_history:
        sev = a.get('severity', 'NONE')
        if order.index(sev) > order.index(worst):
            worst = sev
    return worst


# ------------------------------------------------------------------ #
# Email sender
# ------------------------------------------------------------------ #
class WeeklyReporter:
    def __init__(self):
        self.sender_email = os.environ.get('EMAIL_SENDER', '')
        self.sender_password = os.environ.get('EMAIL_PASSWORD', '')
        self.fallback_recipients = [
            r.strip() for r in
            os.environ.get('EMAIL_RECIPIENTS', '').split(',')
            if r.strip()
        ]
        self.alarm_system = FloodAlarmSystem()

    def _get_recipients(self) -> List[str]:
        subs = self.alarm_system.get_subscribers()
        emails = [s['email'] for s in subs]
        return emails if emails else self.fallback_recipients

    def send_weekly_report(self) -> dict:
        """
        Gather last 7 days of alarms, build custom HTML reports filtered by
        subscriber city choices, and send them. Returns a status dict.
        """
        week_end = datetime.now()
        week_start = week_end - timedelta(days=7)
        ws_str = week_start.strftime('%d %b %Y')
        we_str = week_end.strftime('%d %b %Y')

        # Filter alarm history to last 7 days
        all_alarms = self.alarm_system.get_alarm_history(limit=200)
        week_alarms = [
            a for a in all_alarms
            if a.get('timestamp', '') >= week_start.isoformat()
        ]

        subscribers = self.alarm_system.get_subscribers()
        
        if not subscribers and not self.fallback_recipients:
            logger.warning("No recipients configured for weekly report.")
            return {'status': 'skipped', 'reason': 'no recipients', 'events': len(week_alarms)}

        # Intercept for Gmail API (highest priority)
        if os.environ.get('GMAIL_REFRESH_TOKEN'):
            sent = []
            failed = []
            if subscribers:
                for sub in subscribers:
                    addr = sub['email']
                    cities = sub.get('cities', [])
                    
                    if cities and "all" not in [c.lower() for c in cities]:
                        user_alarms = [
                            a for a in week_alarms
                            if any(c.lower() in a.get('location_name', '').lower() for c in cities)
                        ]
                    else:
                        user_alarms = week_alarms
                        
                    html_body = build_html_report(user_alarms, ws_str, we_str, cities)
                    subject = (
                        f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                        f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
                    )
                    res = self._send_email_via_gmail_api(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Gmail API error')})
            else:
                html_body = build_html_report(week_alarms, ws_str, we_str, None)
                subject = (
                    f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                    f"| {len(week_alarms)} event{'s' if len(week_alarms) != 1 else ''}"
                )
                for addr in self.fallback_recipients:
                    res = self._send_email_via_gmail_api(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Gmail API error')})
            return {
                'status': 'sent',
                'sent_to': sent,
                'failed': failed,
                'events_included': len(week_alarms),
                'period': f'{ws_str} to {we_str}',
            }

        # Intercept for Brevo API
        if os.environ.get('BREVO_API_KEY'):
            sent = []
            failed = []
            if subscribers:
                for sub in subscribers:
                    addr = sub['email']
                    cities = sub.get('cities', [])
                    
                    if cities and "all" not in [c.lower() for c in cities]:
                        user_alarms = [
                            a for a in week_alarms
                            if any(c.lower() in a.get('location_name', '').lower() for c in cities)
                        ]
                    else:
                        user_alarms = week_alarms
                        
                    html_body = build_html_report(user_alarms, ws_str, we_str, cities)
                    subject = (
                        f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                        f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
                    )
                    res = self._send_email_via_brevo(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Brevo error')})
            else:
                html_body = build_html_report(week_alarms, ws_str, we_str, None)
                subject = (
                    f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                    f"| {len(week_alarms)} event{'s' if len(week_alarms) != 1 else ''}"
                )
                for addr in self.fallback_recipients:
                    res = self._send_email_via_brevo(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Brevo error')})
            return {
                'status': 'sent',
                'sent_to': sent,
                'failed': failed,
                'events_included': len(week_alarms),
                'period': f'{ws_str} to {we_str}',
            }

        # Intercept for Resend API
        if os.environ.get('RESEND_API_KEY'):
            sent = []
            failed = []
            if subscribers:
                for sub in subscribers:
                    addr = sub['email']
                    cities = sub.get('cities', [])
                    
                    if cities and "all" not in [c.lower() for c in cities]:
                        user_alarms = [
                            a for a in week_alarms
                            if any(c.lower() in a.get('location_name', '').lower() for c in cities)
                        ]
                    else:
                        user_alarms = week_alarms
                        
                    html_body = build_html_report(user_alarms, ws_str, we_str, cities)
                    subject = (
                        f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                        f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
                    )
                    res = self._send_email_via_resend(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Resend error')})
            else:
                html_body = build_html_report(week_alarms, ws_str, we_str, None)
                subject = (
                    f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                    f"| {len(week_alarms)} event{'s' if len(week_alarms) != 1 else ''}"
                )
                for addr in self.fallback_recipients:
                    res = self._send_email_via_resend(addr, subject, html_body)
                    if res.get('status') == 'sent':
                        sent.append(addr)
                    else:
                        failed.append({'email': addr, 'error': res.get('error', 'Unknown Resend error')})
            return {
                'status': 'sent',
                'sent_to': sent,
                'failed': failed,
                'events_included': len(week_alarms),
                'period': f'{ws_str} to {we_str}',
            }

        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping actual send.")
            html_body = build_html_report(week_alarms, ws_str, we_str, None)
            recipients = [s['email'] for s in subscribers] if subscribers else self.fallback_recipients
            return {
                'status': 'skipped',
                'reason': 'email credentials not configured',
                'events': len(week_alarms),
                'recipients': recipients,
                'html_preview': html_body,
            }

        sent = []
        failed = []
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10.0) as server:
                server.login(self.sender_email, self.sender_password)
                
                if subscribers:
                    for sub in subscribers:
                        addr = sub['email']
                        cities = sub.get('cities', [])
                        
                        # Filter alarms by subscriber's selected cities
                        if cities and "all" not in [c.lower() for c in cities]:
                            user_alarms = [
                                a for a in week_alarms
                                if any(c.lower() in a.get('location_name', '').lower() for c in cities)
                            ]
                        else:
                            user_alarms = week_alarms
                            
                        html_body = build_html_report(user_alarms, ws_str, we_str, cities)
                        subject = (
                            f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                            f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
                        )
                        
                        try:
                            msg = MIMEMultipart('alternative')
                            msg['Subject'] = subject
                            msg['From'] = f"FloodWatch AI <{self.sender_email}>"
                            msg['To'] = addr
                            msg.attach(MIMEText(html_body, 'html'))
                            server.sendmail(self.sender_email, addr, msg.as_string())
                            sent.append(addr)
                            logger.info(f"Report sent to {addr} (filtered for cities: {cities})")
                        except Exception as e:
                            failed.append({'email': addr, 'error': str(e)})
                            logger.error(f"Failed to send to {addr}: {e}")
                else:
                    html_body = build_html_report(week_alarms, ws_str, we_str, None)
                    subject = (
                        f"🌊 FloodWatch AI — Weekly Report ({ws_str} to {we_str}) "
                        f"| {len(week_alarms)} event{'s' if len(week_alarms) != 1 else ''}"
                    )
                    for addr in self.fallback_recipients:
                        try:
                            msg = MIMEMultipart('alternative')
                            msg['Subject'] = subject
                            msg['From'] = f"FloodWatch AI <{self.sender_email}>"
                            msg['To'] = addr
                            msg.attach(MIMEText(html_body, 'html'))
                            server.sendmail(self.sender_email, addr, msg.as_string())
                            sent.append(addr)
                            logger.info(f"Report sent to fallback {addr}")
                        except Exception as e:
                            failed.append({'email': addr, 'error': str(e)})
                            logger.error(f"Failed to send to fallback {addr}: {e}")
                            
        except Exception as smtp_err:
            logger.error(f"SMTP connection failed: {smtp_err}")
            return {'status': 'error', 'error': str(smtp_err)}

        return {
            'status': 'sent',
            'sent_to': sent,
            'failed': failed,
            'events_included': len(week_alarms),
            'period': f'{ws_str} to {we_str}',
        }

    def get_report_preview(self) -> str:
        """Return the HTML for the current week's report (no email sent)."""
        week_end = datetime.now()
        week_start = week_end - timedelta(days=7)
        all_alarms = self.alarm_system.get_alarm_history(limit=200)
        week_alarms = [
            a for a in all_alarms
            if a.get('timestamp', '') >= week_start.isoformat()
        ]
        return build_html_report(
            week_alarms,
            week_start.strftime('%d %b %Y'),
            week_end.strftime('%d %b %Y'),
            None
        )

    def send_welcome_email(self, email: str, name: str = '', cities: list = None) -> dict:
        """Send a confirmation welcome email immediately to the subscriber."""
        cities_str = ", ".join(cities) if cities else "All monitored cities"
        subject = "🌊 Welcome to FloodWatch AI Alerts!"
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to FloodWatch AI</title>
</head>
<body style="margin:0; padding:0; background:#f0f4f8; font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8; padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#ffffff; border-radius:16px; overflow:hidden;
              box-shadow:0 8px 24px rgba(0,0,0,0.12); max-width:600px; width:100%;">
  <tr>
    <td style="background:linear-gradient(135deg,#0052a3,#00b3b3);
               padding:36px 40px; text-align:center;">
      <div style="font-size:36px; margin-bottom:6px;">🌊</div>
      <h1 style="color:#ffffff; margin:0; font-size:26px; font-weight:700;
                 letter-spacing:-0.5px;">Subscription Confirmed</h1>
    </td>
  </tr>
  <tr>
    <td style="padding:40px; color:#1e293b; font-size:15px; line-height:1.6;">
      <p style="margin:0 0 16px;">Hello {name or 'there'},</p>
      <p style="margin:0 0 16px;">
        Thank you for subscribing to **FloodWatch AI**. Your subscription has been successfully confirmed.
      </p>
      <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:20px; margin:24px 0;">
        <h4 style="margin:0 0 10px; color:#0052a3; font-size:16px;">Subscription Details:</h4>
        <p style="margin:0 0 8px;"><b>Email:</b> {email}</p>
        <p style="margin:0;"><b>Monitored Cities:</b> {cities_str}</p>
      </div>
      <p style="margin:0 0 16px;">
        You will receive a weekly digest every **Monday at 08:00 IST** containing water coverage analyses and flood detection logs for your chosen cities.
      </p>
      <p style="margin:0 0 24px;">
        If you wish to update your monitored cities or unsubscribe, you can do so at any time through the dashboard.
      </p>
      <hr style="border:none; border-top:1px solid #e2e8f0; margin:0 0 20px;">
      <p style="margin:0; font-size:12px; color:#94a3b8; text-align:center;">
        FloodWatch AI — India Flood Monitoring System
      </p>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""

        # Intercept for Gmail API (highest priority — sends via Google's own servers)
        if os.environ.get('GMAIL_REFRESH_TOKEN'):
            return self._send_email_via_gmail_api(email, subject, html)

        # Intercept for Brevo API
        if os.environ.get('BREVO_API_KEY'):
            return self._send_email_via_brevo(email, subject, html)

        # Intercept for Resend API
        if os.environ.get('RESEND_API_KEY'):
            return self._send_email_via_resend(email, subject, html)

        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping welcome email.")
            return {'status': 'skipped', 'reason': 'email credentials not configured'}

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10.0) as server:
                server.login(self.sender_email, self.sender_password)
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"FloodWatch AI <{self.sender_email}>"
                msg['To'] = email
                msg.attach(MIMEText(html, 'html'))
                server.sendmail(self.sender_email, email, msg.as_string())
                logger.info(f"Welcome email sent successfully to {email}")
                return {'status': 'sent', 'email': email}
        except Exception as e:
            logger.error(f"Failed to send welcome email to {email}: {e}")
            return {'status': 'error', 'error': str(e)}

    def send_personalized_report_to_email(self, email: str, name: str = '', cities: list = None) -> dict:
        """
        Build and send a weekly-format report containing the last 7 days of alarms
        specifically filtered for the given cities to a single email address.
        """
        week_end = datetime.now()
        week_start = week_end - timedelta(days=7)
        ws_str = week_start.strftime('%d %b %Y')
        we_str = week_end.strftime('%d %b %Y')

        # Filter alarm history to last 7 days
        all_alarms = self.alarm_system.get_alarm_history(limit=200)
        week_alarms = [
            a for a in all_alarms
            if a.get('timestamp', '') >= week_start.isoformat()
        ]

        # Filter alarms by selected cities
        if cities and "all" not in [c.lower() for c in cities]:
            user_alarms = [
                a for a in week_alarms
                if any(c.lower() in a.get('location_name', '').lower() for c in cities)
            ]
        else:
            user_alarms = week_alarms

        html_body = build_html_report(user_alarms, ws_str, we_str, cities)
        subject = (
            f"🌊 FloodWatch AI — Initial Flood Report ({ws_str} to {we_str}) "
            f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
        )

        # Intercept for Gmail API (highest priority — sends via Google's own servers)
        if os.environ.get('GMAIL_REFRESH_TOKEN'):
            return self._send_email_via_gmail_api(email, subject, html_body)

        # Intercept for Brevo API
        if os.environ.get('BREVO_API_KEY'):
            return self._send_email_via_brevo(email, subject, html_body)

        # Intercept for Resend API
        if os.environ.get('RESEND_API_KEY'):
            return self._send_email_via_resend(email, subject, html_body)

        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping personalized report.")
            return {'status': 'skipped', 'reason': 'email credentials not configured'}

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10.0) as server:
                server.login(self.sender_email, self.sender_password)
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"FloodWatch AI <{self.sender_email}>"
                msg['To'] = email
                msg.attach(MIMEText(html_body, 'html'))
                server.sendmail(self.sender_email, email, msg.as_string())
                logger.info(f"Initial personalized report sent successfully to {email} for cities: {cities}")
                return {'status': 'sent', 'email': email, 'events': len(user_alarms)}
        except Exception as e:
            logger.error(f"Failed to send personalized report to {email}: {e}")
            return {'status': 'error', 'error': str(e)}

    def _send_email_via_resend(self, to_email: str, subject: str, html_body: str) -> dict:
        """Send email via Resend's HTTPS REST API to bypass SMTP port blocks on Render."""
        api_key = os.environ.get('RESEND_API_KEY')
        if not api_key:
            return {'status': 'skipped', 'reason': 'no resend api key'}
            
        sender = os.environ.get('EMAIL_SENDER', 'onboarding@resend.dev')
        if not sender or '@' not in sender:
            sender = 'onboarding@resend.dev'
            
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "from": f"FloodWatch AI <{sender}>",
            "to": to_email,
            "subject": subject,
            "html": html_body
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10.0)
            if response.status_code in (200, 201):
                logger.info(f"Email sent successfully via Resend API to {to_email}")
                return {'status': 'sent', 'email': to_email}
            else:
                logger.error(f"Resend API error: {response.text}")
                return {'status': 'error', 'error': f"Resend API returned {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"Failed to send email via Resend API to {to_email}: {e}")
            return {'status': 'error', 'error': str(e)}

    def _send_email_via_brevo(self, to_email: str, subject: str, html_body: str) -> dict:
        """Send email via Brevo's HTTPS REST API to bypass SMTP port blocks on Render."""
        api_key = os.environ.get('BREVO_API_KEY')
        if not api_key:
            return {'status': 'skipped', 'reason': 'no brevo api key'}
            
        sender_email = os.environ.get('EMAIL_SENDER', 'dhairyasen7@gmail.com')
        if not sender_email or '@' not in sender_email:
            sender_email = 'dhairyasen7@gmail.com'
            
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "sender": {
                "name": "FloodWatch AI",
                "email": sender_email
            },
            "to": [
                {
                    "email": to_email
                }
            ],
            "subject": subject,
            "htmlContent": html_body
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10.0)
            if response.status_code in (200, 201, 202):
                logger.info(f"Email sent successfully via Brevo API to {to_email}")
                return {'status': 'sent', 'email': to_email}
            else:
                logger.error(f"Brevo API error: {response.text}")
                return {'status': 'error', 'error': f"Brevo API returned {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"Failed to send email via Brevo API to {to_email}: {e}")
            return {'status': 'error', 'error': str(e)}

    def _send_email_via_gmail_api(self, to_email: str, subject: str, html_body: str) -> dict:
        """Send email via Gmail REST API using OAuth2 refresh token.
        Sends directly through Google's servers — no SMTP, no DMARC issues, no rate limits.
        Required env vars: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, EMAIL_SENDER
        """
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        client_id     = os.environ.get('GMAIL_CLIENT_ID')
        client_secret = os.environ.get('GMAIL_CLIENT_SECRET')
        refresh_token = os.environ.get('GMAIL_REFRESH_TOKEN')
        sender_email  = os.environ.get('EMAIL_SENDER', 'dhairyasen7@gmail.com')

        if not all([client_id, client_secret, refresh_token]):
            return {'status': 'skipped', 'reason': 'Gmail API credentials not configured'}

        # Step 1: Get a fresh access token using the refresh token
        try:
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id':     client_id,
                    'client_secret': client_secret,
                    'refresh_token': refresh_token,
                    'grant_type':    'refresh_token',
                },
                timeout=10.0
            )
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            if not access_token:
                logger.error(f"Gmail API token refresh failed: {token_data}")
                return {'status': 'error', 'error': f"Token refresh failed: {token_data}"}
        except Exception as e:
            logger.error(f"Gmail API token refresh exception: {e}")
            return {'status': 'error', 'error': str(e)}

        # Step 2: Build the RFC 2822 email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"FloodWatch AI <{sender_email}>"
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        # Step 3: Base64url-encode the raw message (Gmail API requirement)
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

        # Step 4: Send via Gmail API
        try:
            send_response = requests.post(
                f'https://gmail.googleapis.com/gmail/v1/users/{sender_email}/messages/send',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type':  'application/json',
                },
                json={'raw': raw_message},
                timeout=15.0
            )
            if send_response.status_code in (200, 201):
                logger.info(f"Email sent successfully via Gmail API to {to_email}")
                return {'status': 'sent', 'email': to_email}
            else:
                logger.error(f"Gmail API send error: {send_response.text}")
                return {'status': 'error', 'error': f"Gmail API returned {send_response.status_code}: {send_response.text}"}
        except Exception as e:
            logger.error(f"Gmail API send exception to {to_email}: {e}")
            return {'status': 'error', 'error': str(e)}