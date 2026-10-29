"""Ekran skrinshoti (bir nechta monitor bo'lsa, hammasi bitta rasmda)."""
import mss
import mss.tools


def take_screenshot() -> tuple[bytes, int, int]:
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # 0 = barcha monitorlar birga
        shot = sct.grab(monitor)
        png = mss.tools.to_png(shot.rgb, shot.size)
        return png, shot.width, shot.height
