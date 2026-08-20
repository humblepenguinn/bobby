from collections.abc import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QMouseEvent,
    QPainter,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SpeechBubble(QFrame):
    dismissed = Signal()
    P = 3  # Pixel block size matching Bobby's sprite pixel grid

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._full_title: str = ""
        self._full_time: str = ""
        self._action_url: str = ""
        self._typewriter_idx: int = 0
        self._bubble_opacity: float = 0.0
        self._fade_callback: Callable[[], None] | None = None
        self._drag_start_pos: QPoint | None = None

        self._typewriter_timer = QTimer(self)
        self._typewriter_timer.setInterval(20)
        self._typewriter_timer.timeout.connect(self._update_typewriter)

        self._init_ui()

    def get_bubble_opacity(self) -> float:
        return self._bubble_opacity

    def set_bubble_opacity(self, opacity: float) -> None:
        self._bubble_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    bubble_opacity = Property(float, get_bubble_opacity, set_bubble_opacity)

    def _init_ui(self) -> None:
        self.setObjectName("SpeechBubbleFrame")
        self.setStyleSheet("""
            QFrame#SpeechBubbleFrame {
                background: transparent;
                border: none;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QPushButton {
                font-family: 'DejaVu Sans Mono', 'Monospace', 'Courier New', monospace;
                font-size: 10px;
                font-weight: bold;
                border-radius: 0px;
                padding: 4px 12px;
            }
            QPushButton#ActionBtn {
                background-color: #f4f4f5;
                color: #09090b;
                border: 2px solid #000000;
            }
            QPushButton#ActionBtn:hover {
                background-color: #ffffff;
                color: #000000;
            }
            QPushButton#ActionBtn:pressed {
                background-color: #e4e4e7;
                color: #09090b;
            }
            QPushButton#DismissBtn {
                background-color: #27272a;
                color: #a1a1aa;
                border: 2px solid #000000;
            }
            QPushButton#DismissBtn:hover {
                background-color: #3f3f46;
                color: #f4f4f5;
            }
        """)

        self.fade_anim = QPropertyAnimation(self, b"bubble_opacity")
        self.fade_anim.finished.connect(self._on_fade_finished)

        tail_h = self.P * 3
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14 + tail_h)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self.badge_label = QLabel("[ UPCOMING ]")
        self.badge_label.setFont(QFont("DejaVu Sans Mono", 8, QFont.Weight.Bold))
        self.badge_label.setStyleSheet("""
            color: #d4d4d8;
            background-color: #27272a;
            border: 1px solid #52525b;
            padding: 1px 5px;
        """)

        self.countdown_label = QLabel("[ IN 10 MINS ]")
        self.countdown_label.setFont(QFont("DejaVu Sans Mono", 8, QFont.Weight.Bold))
        self.countdown_label.setStyleSheet("""
            color: #fb923c;
            background-color: #27272a;
            border: 1px solid #fb923c;
            padding: 1px 5px;
        """)
        self.countdown_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header.addWidget(self.badge_label)
        header.addStretch()
        header.addWidget(self.countdown_label)
        layout.addLayout(header)

        self.title_label = QLabel("Event Summary")
        self.title_label.setFont(QFont("DejaVu Sans Mono", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #f4f4f5; margin-top: 2px;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.time_label = QLabel("> 10:00 AM - 10:30 AM")
        self.time_label.setFont(QFont("DejaVu Sans Mono", 8))
        self.time_label.setStyleSheet("color: #a1a1aa;")
        self.time_label.setWordWrap(True)
        layout.addWidget(self.time_label)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(8)

        self.dismiss_btn = QPushButton("DISMISS")
        self.dismiss_btn.setObjectName("DismissBtn")
        self.dismiss_btn.setCursor(Qt.PointingHandCursor)
        self.dismiss_btn.clicked.connect(self.dismissed.emit)

        self.action_btn = QPushButton("JOIN MEETING >")
        self.action_btn.setObjectName("ActionBtn")
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action_click)
        self.action_btn.hide()

        buttons.addWidget(self.dismiss_btn)
        buttons.addStretch()
        buttons.addWidget(self.action_btn)
        layout.addLayout(buttons)

        self.setFixedWidth(310)

    def paintEvent(self, event) -> None:
        if self._bubble_opacity <= 0.01:
            return

        painter = QPainter(self)
        if not painter.isActive():
            return

        painter.setOpacity(self._bubble_opacity)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        p = self.P
        w = self.width()
        h = self.height()
        tail_h = p * 3
        box_h = h - tail_h

        bg_color = QColor("#18181b")
        border_color = QColor("#000000")
        accent_color = QColor("#52525b")

        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QBrush(border_color))
        painter.drawRect(p, 0, w - 2 * p, box_h)
        painter.drawRect(0, p, w, box_h - 2 * p)

        cx = w // 2
        painter.drawRect(cx - 3 * p, box_h, 6 * p, p)
        painter.drawRect(cx - 2 * p, box_h + p, 4 * p, p)
        painter.drawRect(cx - p, box_h + 2 * p, 2 * p, p)

        painter.setBrush(QBrush(bg_color))
        painter.drawRect(2 * p, p, w - 4 * p, box_h - 2 * p)
        painter.drawRect(p, 2 * p, w - 2 * p, box_h - 4 * p)

        painter.drawRect(cx - 2 * p, box_h - p, 4 * p, 2 * p)
        painter.drawRect(cx - p, box_h + p, 2 * p, p)

        painter.setBrush(QBrush(accent_color))
        painter.drawRect(2 * p, p, w - 4 * p, p)

        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._notify_parent_mask()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._notify_parent_mask()

    def _notify_parent_mask(self) -> None:
        win = self.window()
        if win and hasattr(win, "_update_input_mask"):
            win._update_input_mask()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_start_pos:
            curr_pos = event.globalPosition().toPoint()
            delta = curr_pos - self._drag_start_pos
            if delta.manhattanLength() > 3:
                card = self.parentWidget()
                if card:
                    card.move(card.pos() + delta)
                self._drag_start_pos = curr_pos
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def set_event(
        self,
        title: str,
        time_str: str,
        countdown_str: str = "in 10 mins",
        action_url: str = "",
        action_text: str = "JOIN MEETING >",
        badge_text: str = "UPCOMING",
    ) -> None:
        self._full_title = title
        self._full_time = time_str
        self._action_url = action_url

        self.badge_label.setText(f"[ {badge_text.upper()} ]")
        self.countdown_label.setText(f"[ {countdown_str.upper()} ]")
        time_display = time_str if time_str.startswith((">", "[")) else f"> {time_str}"
        self.time_label.setText(time_display)

        if action_text:
            btn_text = action_text.upper()
            if not btn_text.endswith(">"):
                btn_text = f"{btn_text} >"
            self.action_btn.setText(btn_text)
            self.action_btn.show()
        elif self._action_url:
            self.action_btn.setText("JOIN MEETING >")
            self.action_btn.show()
        else:
            self.action_btn.hide()

        self._typewriter_idx = 0
        self.title_label.setText("")
        self._typewriter_timer.start()

    def fade_in(self, duration: int = 350) -> None:
        self.show()
        self.fade_anim.stop()
        self.fade_anim.setDuration(duration)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_anim.setStartValue(self._bubble_opacity)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def fade_out(
        self, duration: int = 250, on_finished: Callable[[], None] | None = None
    ) -> None:
        self.fade_anim.stop()
        self._fade_callback = on_finished
        self.fade_anim.setDuration(duration)
        self.fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self.fade_anim.setStartValue(self._bubble_opacity)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

    def _on_fade_finished(self) -> None:
        if self._fade_callback:
            callback = self._fade_callback
            self._fade_callback = None
            callback()
        self._notify_parent_mask()

    def _update_typewriter(self) -> None:
        if self._typewriter_idx < len(self._full_title):
            self._typewriter_idx += 1
            self.title_label.setText(self._full_title[: self._typewriter_idx])
        else:
            self._typewriter_timer.stop()

    def _on_action_click(self) -> None:
        if self._action_url:
            QDesktopServices.openUrl(QUrl(self._action_url))
