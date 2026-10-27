"""Neural models for the privileged-entity training pipeline."""

from .teacher import CustomTransformerLayer, OmniscientEntityTeacher, TeacherOutput

__all__ = ["CustomTransformerLayer", "OmniscientEntityTeacher", "TeacherOutput"]
