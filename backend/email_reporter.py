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
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import List, Optional

from alarm_system import FloodAlarmSystem, ALARM_COLORS, ALARM_ICONS

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# HTML report builder
# ------------------------------------------------------------------ #
def build_html_report(alarm_history: list, week_start: str, week_end: str) -> str:
    """Render a full HTML email from a list of alarm dicts."""

    # Summary counts
    counts = {'NONE': 0, 'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
    for a in alarm_history:
        sev = a.get('severity', 'NONE')
        counts[sev] = counts.get(sev, 0) + 1

    total = len(alarm_history)
    worst = _worst_severity(alarm_history)
    worst_color = ALARM_COLORS.get(worst, '#64748b')
    worst_icon = ALARM_ICONS.get(worst, '✅')

    # Build alarm rows
    rows_html = ''
    if not alarm_history:
        rows_html = '''
        <tr>
            <td colspan="5" style="text-align:center; padding:24px; color:#64748b; font-style:italic;">
                No flood events recorded this week.
            </td>
        </tr>'''
    else:
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

  <!-- Events table -->
  <tr>
    <td style="padding:28px 40px 0;">
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
      </table>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:32px 40px;">
      <hr style="border:none; border-top:1px solid #e2e8f0; margin:0 0 20px;">
      <p style="margin:0; font-size:12px; color:#94a3b8; text-align:center; line-height:1.8;">
        🛰️ Data source: Sentinel-2 (10m resolution) via Google Earth Engine<br>
        📍 FloodWatch AI — India Flood Monitoring System<br>
        Generated automatically on {datetime.now().strftime('%d %b %Y at %H:%M IST')}
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

        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping actual send.")
            html_body = build_html_report(week_alarms, ws_str, we_str)
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
                            
                        html_body = build_html_report(user_alarms, ws_str, we_str)
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
                    html_body = build_html_report(week_alarms, ws_str, we_str)
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
        )

    def send_welcome_email(self, email: str, name: str = '', cities: list = None) -> dict:
        """Send a confirmation welcome email immediately to the subscriber."""
        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping welcome email.")
            return {'status': 'skipped', 'reason': 'email credentials not configured'}
            
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
        if not self.sender_email or not self.sender_password:
            logger.warning("EMAIL_SENDER / EMAIL_PASSWORD not set; skipping personalized report.")
            return {'status': 'skipped', 'reason': 'email credentials not configured'}

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

        html_body = build_html_report(user_alarms, ws_str, we_str)
        subject = (
            f"🌊 FloodWatch AI — Initial Flood Report ({ws_str} to {we_str}) "
            f"| {len(user_alarms)} event{'s' if len(user_alarms) != 1 else ''}"
        )

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