from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap


class AnimState(Enum):
    IDLE = "idle"
    WALK = "walk"
    JUMP = "jump"
    FALL = "fall"
    LAND = "land"
    FLAP = "flap"
    TURN = "turn"
    CROUCH = "crouch"
    SPIN_ATTACK = "spin_attack"
    ROLL = "roll"


class SpriteAnimator(QObject):
    frame_changed = Signal(QPixmap)

    def __init__(
        self,
        assets_dir: Path,
        frame_size: int = 64,
        scale: float = 2.5,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.assets_dir = Path(assets_dir)
        if not self.assets_dir.is_dir():
            raise FileNotFoundError(f"Missing assets directory: {assets_dir}")
        self.frame_size = frame_size
        self.scale = scale
        self._animations: dict[AnimState, list[QPixmap]] = {}
        self.current_state: AnimState = AnimState.IDLE
        self._frame_idx: int = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        self._load_sprites()

    def _load_sprites(self) -> None:
        for path in self.assets_dir.glob("*.png"):
            try:
                state = AnimState(path.stem)
            except ValueError:
                continue

            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                raise ValueError(f"Corrupt image file: {path}")

            scaled_dim = int(self.frame_size * self.scale)
            num_frames = max(1, pixmap.width() // self.frame_size)
            frames = [
                pixmap.copy(
                    i * self.frame_size, 0, self.frame_size, self.frame_size
                ).scaled(
                    scaled_dim,
                    scaled_dim,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                for i in range(num_frames)
            ]
            self._animations[state] = frames

        if not self._animations:
            raise FileNotFoundError(
                f"No valid sprite assets found in {self.assets_dir}"
            )

    def set_animation(self, state: AnimState, interval_ms: int = 150) -> None:
        if state not in self._animations:
            raise KeyError(f"Animation state missing: {state}")

        self.current_state = state
        self._frame_idx = 0
        self._timer.setInterval(interval_ms)
        if not self._timer.isActive():
            self._timer.start()
        self._emit_frame()

    def _next_frame(self) -> None:
        frames = self._animations[self.current_state]
        self._frame_idx = (self._frame_idx + 1) % len(frames)
        self._emit_frame()

    def _emit_frame(self) -> None:
        frames = self._animations[self.current_state]
        self.frame_changed.emit(frames[self._frame_idx])

    def get_current_pixmap(self) -> QPixmap:
        return self._animations[self.current_state][self._frame_idx]
