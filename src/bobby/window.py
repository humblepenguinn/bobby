import random
from enum import Enum, auto

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPixmap, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from bobby.animator import AnimState, SpriteAnimator
from bobby.bubble import SpeechBubble

INFORMING_GESTURES = [AnimState.IDLE, AnimState.FLAP, AnimState.TURN, AnimState.CROUCH]
TRICK_GESTURES = [AnimState.SPIN_ATTACK, AnimState.ROLL, AnimState.JUMP]


class SequencePhase(Enum):
    IDLE = auto()
    WALK_IN = auto()
    JUMP_UP = auto()
    FALL_DOWN = auto()
    LAND = auto()
    EXIT = auto()


class Avatar(QLabel):
    clicked = Signal()

    def __init__(self, animator: SpriteAnimator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.animator = animator
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._drag_start_pos: QPoint | None = None
        self._dragged: bool = False

        self.animator.frame_changed.connect(self._on_frame_changed)
        pixmap = self.animator.get_current_pixmap()
        if pixmap:
            self.setPixmap(pixmap)

    def _on_frame_changed(self, pixmap: QPixmap) -> None:
        self.setPixmap(pixmap)
        self.adjustSize()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            self._dragged = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_start_pos:
            curr_pos = event.globalPosition().toPoint()
            delta = curr_pos - self._drag_start_pos
            if delta.manhattanLength() > 3:
                self._dragged = True
                card = self.parentWidget()
                if card:
                    card.move(card.pos() + delta)
                self._drag_start_pos = curr_pos
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if not self._dragged:
                self.clicked.emit()
            self._drag_start_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class NotificationCard(QWidget):
    def __init__(self, animator: SpriteAnimator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)

        self.bubble = SpeechBubble(self)
        layout.addWidget(self.bubble, 0, Qt.AlignHCenter)

        self.avatar = Avatar(animator, self)
        layout.addWidget(self.avatar, 0, Qt.AlignHCenter)

        self.setFixedSize(340, 360)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        win = self.window()
        if win and hasattr(win, "_update_input_mask"):
            win._update_input_mask()


class OverlayWindow(QWidget):
    def __init__(self, assets_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.animator = SpriteAnimator(assets_dir=assets_dir, parent=self)
        self.phase = SequencePhase.IDLE

        self._gesture_timer = QTimer(self)
        self._gesture_timer.setInterval(3600)
        self._gesture_timer.timeout.connect(self._play_random_gesture)

        self._init_ui()

        self._anim = QPropertyAnimation(self.card, b"pos")
        self._anim.finished.connect(self._on_animation_finished)
        self._anim.valueChanged.connect(lambda _: self._update_input_mask())

        self._card_fade_anim = QPropertyAnimation(self.card.opacity_effect, b"opacity")
        self._card_fade_anim.finished.connect(self._on_exit_fade_finished)

    def _init_ui(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_AlwaysStackOnTop, True)
        self.setStyleSheet("background: transparent;")

        self.card = NotificationCard(self.animator, self)
        self.bubble = self.card.bubble
        self.avatar = self.card.avatar
        self.avatar.clicked.connect(self._on_avatar_clicked)
        self.bubble.dismissed.connect(self.hide_notification)

        self._update_overlay_geometry()
        self.card.move(self.width() + 10, self.height() - self.card.height())

    def _update_overlay_geometry(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())

    def _update_input_mask(self) -> None:
        if not self.isVisible() or self.phase == SequencePhase.IDLE:
            self.clearMask()
            return

        if self.card.opacity_effect.opacity() < 0.05:
            self.clearMask()
            return

        card_pos = self.card.pos()
        region = QRegion()

        if self.bubble.isVisible() and self.bubble.get_bubble_opacity() > 0.01:
            region = region.united(QRegion(self.bubble.geometry().translated(card_pos)))

        region = region.united(QRegion(self.avatar.geometry().translated(card_pos)))
        self.setMask(region)

    def show_notification(
        self,
        title: str,
        time_str: str,
        countdown_str: str = "in 10 mins",
        action_url: str = "",
        action_text: str = "Join Meeting",
        badge_text: str = "UPCOMING",
    ) -> None:
        self._pending_title = title
        self._pending_time = time_str
        self._pending_countdown = countdown_str
        self._pending_action_url = action_url
        self._pending_action_text = action_text
        self._pending_badge_text = badge_text

        self._gesture_timer.stop()
        self.card.opacity_effect.setOpacity(1.0)
        self.bubble.set_bubble_opacity(0.0)
        self.bubble.hide()
        self._update_overlay_geometry()

        card_h = self.card.height()
        card_w = self.card.width()
        self._ground_y = self.height() - card_h - 10
        self._start_x = self.width() + 10
        self._center_x = (self.width() - card_w) // 2
        self._apex_y = self._ground_y - 110

        self.card.move(QPoint(self._start_x, self._ground_y))
        self.show()
        self.raise_()
        self._update_input_mask()

        self.animator.set_animation(AnimState.WALK, interval_ms=100)
        self.phase = SequencePhase.WALK_IN
        self._anim.stop()
        self._anim.setDuration(1300)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.setStartValue(QPoint(self._start_x, self._ground_y))
        self._anim.setEndValue(QPoint(self._center_x, self._ground_y))
        self._anim.start()

    def _on_animation_finished(self) -> None:
        if self.phase == SequencePhase.WALK_IN:
            self.phase = SequencePhase.JUMP_UP
            self.animator.set_animation(AnimState.JUMP, interval_ms=100)
            self._anim.setDuration(380)
            self._anim.setEasingCurve(QEasingCurve.OutQuad)
            self._anim.setStartValue(QPoint(self._center_x, self._ground_y))
            self._anim.setEndValue(QPoint(self._center_x, self._apex_y))
            self._anim.start()

        elif self.phase == SequencePhase.JUMP_UP:
            self.phase = SequencePhase.FALL_DOWN
            self.animator.set_animation(AnimState.FALL, interval_ms=100)
            self._anim.setDuration(340)
            self._anim.setEasingCurve(QEasingCurve.InQuad)
            self._anim.setStartValue(QPoint(self._center_x, self._apex_y))
            self._anim.setEndValue(QPoint(self._center_x, self._ground_y))
            self._anim.start()

        elif self.phase == SequencePhase.FALL_DOWN:
            self.phase = SequencePhase.LAND
            self.animator.set_animation(AnimState.LAND, interval_ms=130)
            QTimer.singleShot(240, self._reveal_speech_bubble)

        self._update_input_mask()

    def _reveal_speech_bubble(self) -> None:
        self.animator.set_animation(AnimState.IDLE, interval_ms=180)
        self.bubble.set_event(
            self._pending_title,
            self._pending_time,
            self._pending_countdown,
            self._pending_action_url,
            self._pending_action_text,
            self._pending_badge_text,
        )
        self.bubble.fade_in(450)
        self._gesture_timer.start()
        self._update_input_mask()

    def _play_random_gesture(self) -> None:
        current = self.animator.current_state
        choices = [g for g in INFORMING_GESTURES if g != current]
        gesture = random.choice(choices) if choices else AnimState.IDLE
        self.animator.set_animation(gesture, interval_ms=140)
        QTimer.singleShot(
            1400, lambda: self.animator.set_animation(AnimState.IDLE, interval_ms=180)
        )

    def hide_notification(self) -> None:
        self._gesture_timer.stop()
        self.bubble.fade_out(200, on_finished=self._start_exit_wave)

    def _start_exit_wave(self) -> None:
        self.bubble.hide()
        self.phase = SequencePhase.EXIT
        self._update_input_mask()
        self.animator.set_animation(AnimState.FLAP, interval_ms=110)

        self._card_fade_anim.stop()
        self._card_fade_anim.setDuration(1000)
        self._card_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._card_fade_anim.setStartValue(1.0)
        self._card_fade_anim.setEndValue(0.0)
        QTimer.singleShot(500, self._trigger_card_fade)

    def _trigger_card_fade(self) -> None:
        if self.phase == SequencePhase.EXIT:
            self._card_fade_anim.start()

    def _on_exit_fade_finished(self) -> None:
        if self.phase == SequencePhase.EXIT:
            self.phase = SequencePhase.IDLE
            self.clearMask()
            self.hide()
            self.card.opacity_effect.setOpacity(1.0)

    def _on_avatar_clicked(self) -> None:
        current = self.animator.current_state
        if current in TRICK_GESTURES:
            next_anim = TRICK_GESTURES[
                (TRICK_GESTURES.index(current) + 1) % len(TRICK_GESTURES)
            ]
        else:
            next_anim = TRICK_GESTURES[0]
        self.animator.set_animation(next_anim, interval_ms=100)
        QTimer.singleShot(
            1200, lambda: self.animator.set_animation(AnimState.IDLE, interval_ms=180)
        )
