"""Kind/Argo sandbox gate for GitOps-native Mandate 22.

The production controller has no Deployment mutation adapter. This integration
suite is intentionally opt-in because it needs a disposable Git server, GitHub
API stub, Argo CD and Kind cluster prepared by the drill harness.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_M22_KIND") != "1",
    reason="set RUN_M22_KIND=1 with the Mandate 22 Git/Argo sandbox",
)


def test_sandbox_contract_is_explicit():
    assert os.getenv("M22_GITOPS_SANDBOX_REPOSITORY")
    assert os.getenv("M22_ARGO_APPLICATION") == "techx-corp"
    assert os.getenv("M22_TARGET") == "product-reviews"
