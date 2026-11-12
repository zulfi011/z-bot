from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(
    "config/experiments/v1_stage1.yaml"
)


def load_experiment_config(
    config_path: str | Path = DEFAULT_CONFIG,
) -> dict:
    """
    Load a research experiment YAML configuration.
    """

    config_path = Path(
        config_path
    )

    if not config_path.exists():
        raise FileNotFoundError(
            f"Experiment config not found: {config_path}"
        )

    with open(
        config_path,
        "r",
        encoding="utf-8",
    ) as file:
        config = yaml.safe_load(
            file
        )

    if not isinstance(
        config,
        dict,
    ):
        raise ValueError(
            "Experiment configuration must be a dictionary."
        )

    return config