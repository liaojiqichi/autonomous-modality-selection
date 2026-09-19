"""A/P richness counts; annotation, validity and evidence fidelity remain separate."""

from autonomous_modality.models import RichnessScores, SolutionRichnessAnnotation

RULE_VERSION = "solution-richness-ap-2.0"


def calculate_richness(annotation: SolutionRichnessAnnotation) -> RichnessScores:
    """Count relevant duplicate groups; do not gate on execution or quality labels."""
    groups = {(i.dimension, i.duplicate_group) for i in annotation.ideas if i.relevant}
    return RichnessScores(
        analytical_approach_count=sum(dimension == "A" for dimension, _ in groups),
        explanatory_perspective_count=sum(dimension == "P" for dimension, _ in groups),
    )
