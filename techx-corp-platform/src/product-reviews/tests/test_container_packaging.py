from pathlib import Path


def test_runtime_observability_module_is_packaged() -> None:
    """The Bedrock adapter imports this module during process startup."""

    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    instructions = dockerfile.read_text(encoding="utf-8").splitlines()

    assert (
        "COPY ./src/product-reviews/llm_observability.py llm_observability.py"
        in instructions
    )
