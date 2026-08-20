import datetime
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from PySide6.QtCore import QObject, QTimer, Signal

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
MEETING_REGEX = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)*(?:meet\.google\.com|zoom\.us|teams\.microsoft\.com|webex\.com)[^\s<>"]+'
)


class Calendar(QObject):
    event_approaching = Signal(dict)
    auth_succeeded = Signal()

    def __init__(
        self,
        credentials_file: Path | str,
        token_file: Path | str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self._service = None
        self._notified_events: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(self.check_upcoming_events)

    def authenticate(self) -> None:
        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing Google Calendar token...")
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Missing OAuth credentials file '{self.credentials_file}'. "
                        "Download credentials.json from Google Cloud Console."
                    )
                logger.info("Opening browser for Google Calendar authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "w") as f:
                f.write(creds.to_json())

        self._service = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        self.auth_succeeded.emit()

    def _on_auth_succeeded(self) -> None:
        self._timer.start()
        self.check_upcoming_events()

    def check_upcoming_events(self) -> list[dict[str, Any]]:
        if not self._service:
            return []

        now = datetime.datetime.now(datetime.UTC)
        max_time = now + datetime.timedelta(minutes=15)

        events_result = (
            self._service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=max_time.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])
        alerts = []

        for event in events:
            parsed = self._parse_event(event, now)
            if not parsed:
                continue

            alerts.append(parsed)
            if parsed["id"] not in self._notified_events:
                self._notified_events.add(parsed["id"])
                self.event_approaching.emit(parsed)

        return alerts

    def _parse_event(
        self, event: dict[str, Any], now: datetime.datetime
    ) -> dict[str, Any] | None:
        event_id = event.get("id")
        summary = event.get("summary", "Untitled Event")
        start = event.get("start", {})
        start_raw = start.get("dateTime") or start.get("date")
        if not start_raw or not event_id:
            return None

        start_dt = datetime.datetime.fromisoformat(start_raw)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=datetime.UTC)

        diff_minutes = int((start_dt - now).total_seconds() // 60)
        if not (0 <= diff_minutes <= 10):
            return None

        video_url = ""
        conf = event.get("conferenceData", {}).get("entryPoints", [])
        for ep in conf:
            if ep.get("entryPointType") == "video":
                video_url = ep.get("uri", "")
                break

        if not video_url:
            search_text = f"{event.get('location', '')} {event.get('description', '')}"
            match = MEETING_REGEX.search(search_text)
            if match:
                video_url = match.group(0)

        html_link = event.get("htmlLink", "")

        if video_url:
            action_url = video_url
            action_text = "Join Meeting"
            is_meeting = True
        elif html_link:
            action_url = html_link
            action_text = "Open Calendar"
            is_meeting = False
        else:
            action_url = ""
            action_text = ""
            is_meeting = False

        local_start = start_dt.astimezone()

        return {
            "id": event_id,
            "summary": summary,
            "time_str": local_start.strftime("%I:%M %p").lstrip("0"),
            "minutes_left": diff_minutes,
            "countdown_str": f"in {diff_minutes} mins"
            if diff_minutes > 0
            else "starting now!",
            "action_url": action_url,
            "action_text": action_text,
            "is_meeting": is_meeting,
        }
