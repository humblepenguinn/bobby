import logging
import random

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor

logger = logging.getLogger(__name__)

IDLE_PROMPTS = [
    ("HEY! 10 MINS IDLE?", "Back to work! Stop being lazy / doomscrolling!"),
    ("BOBBY SEES YOU!", "Are you doomscrolling on your phone? Get back to work!"),
    ("PROCRASTINATION DETECTED!", "Time to be productive! Back to code!"),
    ("NO LAZINESS ALLOWED!", "Bobby detected inactivity. Focus time!"),
    ("STOP SLACKING OFF!", "Get back to work and finish those tasks!"),
    ("ARE YOU AFK OR LAZY?", "Time to get back to the keyboard!"),
]


class SystemIdleMonitor(QObject):
    idle_prompt_triggered = Signal(str, str)

    def __init__(
        self,
        idle_threshold_seconds: float = 600.0,
        check_interval_ms: int = 1000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.idle_threshold_seconds = idle_threshold_seconds
        self.check_interval_ms = check_interval_ms
        self._idle_seconds: float = 0.0
        self._last_mouse_pos: QPoint | None = None
        self._prompted: bool = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.check_interval_ms)
        self._timer.timeout.connect(self._check_mouse)

    def start(self) -> None:
        self._last_mouse_pos = QCursor.pos()
        self._idle_seconds = 0.0
        self._prompted = False
        self._timer.start()
        logger.info(
            "idle monitor started (threshold: %.0fs)", self.idle_threshold_seconds
        )

    def stop(self) -> None:
        self._timer.stop()

    def _check_mouse(self) -> None:
        curr_pos = QCursor.pos()

        if self._last_mouse_pos is not None and curr_pos != self._last_mouse_pos:
            if self._idle_seconds >= 1.0:
                logger.debug(
                    "mouse moved, resetting idle (was %.0fs)", self._idle_seconds
                )
            self._last_mouse_pos = curr_pos
            self._idle_seconds = 0.0
            self._prompted = False
            return

        self._last_mouse_pos = curr_pos
        self._idle_seconds += self.check_interval_ms / 1000.0
        logger.debug(
            "idle: %.0f / %.0fs", self._idle_seconds, self.idle_threshold_seconds
        )

        if self._idle_seconds >= self.idle_threshold_seconds and not self._prompted:
            self._prompted = True
            title, message = random.choice(IDLE_PROMPTS)
            logger.info("idle threshold reached, triggering prompt")
            self.idle_prompt_triggered.emit(title, message)
