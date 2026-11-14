"""Kural kataloğu panelde ve AugeLab Studio'daki motorda aynıdır: motor/yangin_motor/katalog.py.

Panel yalnızca kataloğu kullanır; modeli yüklemez (model yalnızca AugeLab Studio'nun içinde açılır)."""
import sys
from pathlib import Path

_motor = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "motor"
if str(_motor) not in sys.path:
    sys.path.insert(0, str(_motor))

from yangin_motor.katalog import *  # noqa: E402,F401,F403
from yangin_motor.katalog import KURAL, KURALLAR  # noqa: E402,F401
