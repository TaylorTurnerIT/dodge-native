"""Synthetic tests load the exact owned runtime files without native imports."""
from pathlib import Path
__path__ = [str(Path(__file__).resolve().parents[2]/"runtime/dodge_rl")]
