import json
import logging
import signal
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMenu,
    QSystemTrayIcon,
)

from bobby.gcal import Calendar
from bobby.idle import SystemIdleMonitor
from bobby.window import OverlayWindow


def _crop_sprite_frame(path: Path) -> QPixmap | None:
    sheet = QPixmap(str(path))
    if sheet.isNull():
        return None

    frame = sheet.copy(0, 0, 64, 64)
    img = frame.toImage()
    w, h = img.width(), img.height()
    min_x, max_x, min_y, max_y = w, 0, h, 0

    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() > 10:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    if min_x > max_x or min_y > max_y:
        return frame

    return frame.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def create_tray_icon(assets_dir: Path | None = None) -> QIcon:
    if assets_dir:
        idle_path = assets_dir / "idle.png"
        cropped = _crop_sprite_frame(idle_path) if idle_path.exists() else None
        if cropped:
            icon = QIcon()
            for size in (16, 20, 22, 24, 32, 48, 64):
                canvas = QPixmap(size, size)
                canvas.fill(Qt.GlobalColor.transparent)
                scaled = cropped.scaled(
                    size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation
                )
                painter = QPainter(canvas)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.drawPixmap(max(1, size // 8), 0, scaled)
                painter.end()
                icon.addPixmap(canvas)
            return icon

    canvas = QPixmap(24, 24)
    canvas.fill(Qt.GlobalColor.transparent)
    return QIcon(canvas)


class Application:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        base_dir = Path(__file__).resolve().parents[2]
        self.assets_dir = base_dir / "assets"

        self.overlay = OverlayWindow(self.assets_dir)

        self.calendar = Calendar(
            credentials_file=base_dir / "credentials.json",
            token_file=base_dir / "token.json",
        )
        self.calendar.event_approaching.connect(self._on_calendar_event)
        self.calendar.auth_succeeded.connect(self.calendar._on_auth_succeeded)

        self.idle_monitor = SystemIdleMonitor(idle_threshold_seconds=0.0)
        self.idle_monitor.idle_prompt_triggered.connect(self._on_idle_prompt)

        self._settings_file = base_dir / "settings.json"
        self._settings = self._load_settings()

        idle_threshold = self._settings.get("idle_threshold_seconds", 0.0)
        if idle_threshold > 0.0:
            self.idle_monitor.idle_threshold_seconds = idle_threshold
            self.idle_monitor.start()

        self._init_system_tray()
        QTimer.singleShot(100, self._init_calendar_auth)

    def _init_calendar_auth(self) -> None:
        logger.info("connecting to google calendar")
        threading.Thread(target=self._run_auth, daemon=True).start()

    def _run_auth(self) -> None:
        try:
            self.calendar.authenticate()
            logger.info("connected to google calendar")
        except FileNotFoundError as e:
            logger.warning("google calendar credentials not found: %s", e)
        except Exception:
            logger.exception("google calendar auth failed")

    def _init_system_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        try:
            self.tray = QSystemTrayIcon(create_tray_icon(self.assets_dir), self.app)
            self.tray.setToolTip("")

            self.tray_menu = QMenu()

            test_action = QAction("Send Notification...", self.tray_menu)
            test_action.triggered.connect(self._show_test_dialog)
            self.tray_menu.addAction(test_action)

            connect_action = QAction("Connect Google Calendar...", self.tray_menu)
            connect_action.triggered.connect(self.connect_google_calendar)
            self.tray_menu.addAction(connect_action)

            self.tray_menu.addSeparator()

            idle_menu = QMenu("Idle Warning After", self.tray_menu)
            self._idle_threshold_actions: list[QAction] = []
            for label, seconds in [
                ("5 minutes", 300.0),
                ("10 minutes", 600.0),
                ("15 minutes", 900.0),
                ("30 minutes", 1800.0),
                ("Disabled", 0.0),
            ]:
                action = QAction(label, idle_menu)
                action.setCheckable(True)
                action.setChecked(
                    seconds == self._settings.get("idle_threshold_seconds", 0.0)
                )
                action.triggered.connect(
                    lambda _, s=seconds, a=action: self._set_idle_threshold(s, a)
                )
                idle_menu.addAction(action)
                self._idle_threshold_actions.append(action)
            self.tray_menu.addMenu(idle_menu)

            self.tray_menu.addSeparator()

            quit_action = QAction("Quit", self.tray_menu)
            quit_action.triggered.connect(self.app.quit)
            self.tray_menu.addAction(quit_action)

            self.tray.setContextMenu(self.tray_menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()
        except Exception as e:  # noqa: BLE001
            logger.warning("system tray unavailable: %s", e)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_test_dialog()

    def _show_test_dialog(self) -> None:
        dialog = QDialog()
        dialog.setWindowTitle("Send Notification")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        dialog.setMinimumWidth(360)

        form = QFormLayout(dialog)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        saved = self._settings.get("notification", {})
        title_edit = QLineEdit(saved.get("title", "Sprint Planning & Design Review"))
        message_edit = QLineEdit(saved.get("message", "11:30 AM - 12:00 PM"))
        badge_edit = QLineEdit(saved.get("badge", "UPCOMING"))
        countdown_edit = QLineEdit(saved.get("countdown", "in 10 mins"))
        action_url_edit = QLineEdit(saved.get("action_url", "https://meet.google.com"))
        action_text_edit = QLineEdit(saved.get("action_text", "Join Meeting"))

        form.addRow("Title", title_edit)
        form.addRow("Message", message_edit)
        form.addRow("Badge", badge_edit)
        form.addRow("Countdown", countdown_edit)
        form.addRow("Action URL", action_url_edit)
        form.addRow("Action Text", action_text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        title = title_edit.text().strip() or "Bobby"
        message = message_edit.text().strip()
        badge = badge_edit.text().strip() or "UPCOMING"
        countdown = countdown_edit.text().strip() or "now"
        action_url = action_url_edit.text().strip()
        action_text = action_text_edit.text().strip()

        self._settings["notification"] = {
            "title": title,
            "message": message,
            "badge": badge,
            "countdown": countdown,
            "action_url": action_url,
            "action_text": action_text,
        }
        self._save_settings()

        self.overlay.show_notification(
            title=title,
            time_str=message,
            badge_text=badge,
            countdown_str=countdown,
            action_url=action_url,
            action_text=action_text,
        )

    def _set_idle_threshold(self, seconds: float, selected: QAction) -> None:
        for action in self._idle_threshold_actions:
            action.setChecked(action is selected)

        if seconds == 0.0:
            self.idle_monitor.stop()
            logger.info("idle monitor disabled")
        else:
            self.idle_monitor.idle_threshold_seconds = seconds
            self.idle_monitor.start()
            logger.info("idle threshold set to %.0fs", seconds)

        self._settings["idle_threshold_seconds"] = seconds
        self._save_settings()

    def _load_settings(self) -> dict:
        try:
            if self._settings_file.exists():
                return json.loads(self._settings_file.read_text())
        except Exception:  # noqa: BLE001
            logger.warning("could not load settings, using defaults")
        return {}

    def _save_settings(self) -> None:
        try:
            self._settings_file.write_text(json.dumps(self._settings, indent=2))
        except Exception:  # noqa: BLE001
            logger.warning("could not save settings")

    def _on_idle_prompt(self, title: str, message: str) -> None:
        self.overlay.show_notification(
            title=title,
            time_str=message,
            countdown_str="10 MINS IDLE",
            action_url="",
            action_text="BACK TO WORK >",
            badge_text="IDLE WARNING",
        )

    def connect_google_calendar(self) -> None:
        def _do_connect() -> None:
            try:
                self.calendar.authenticate()
            except Exception:
                logger.exception("google calendar reconnect failed")

        threading.Thread(target=_do_connect, daemon=True).start()

    def _on_calendar_event(self, event: dict) -> None:
        self.overlay.show_notification(
            title=event.get("summary", "Upcoming Event"),
            time_str=event.get("time_str", ""),
            countdown_str=event.get("countdown_str", "in 10 mins"),
            action_url=event.get("action_url", ""),
            action_text=event.get("action_text", "Open Calendar"),
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("")
    app.setApplicationDisplayName("")
    app.setQuitOnLastWindowClosed(False)

    signal.signal(signal.SIGINT, lambda *_: (QApplication.quit(), sys.exit(0)))

    # allow ctrl+c to propagate through the qt event loop
    sig_timer = QTimer(app)
    sig_timer.start(250)
    sig_timer.timeout.connect(lambda: None)

    _bobby_app = Application(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
