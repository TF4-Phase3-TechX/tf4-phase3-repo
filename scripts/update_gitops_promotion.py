#!/usr/bin/env python3
"""Apply one source-repository promotion to a GitOps checkout."""

import argparse
import json
import re
import tempfile
from pathlib import Path


IMAGE_REVISIONS = Path("environments/production/image-revisions.yaml")
APPLICATIONS = Path("argocd/root-resources/applications.yaml")
CHART_REPOSITORY = "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo.git"


def update_revisions(gitops_dir, services, digests, image_tag, source_sha, chart_changed):
    gitops_dir = Path(gitops_dir)
    if services:
        path = gitops_dir / IMAGE_REVISIONS
        text = path.read_text()
        for service in services:
            digest = digests.get(service)
            if not digest:
                raise SystemExit(f"missing digest for promoted service {service}")
            tag = f"{image_tag}-{service}"
            pattern = (
                rf'(\n  {re.escape(service)}:\n'
                rf'    imageOverride:\n'
                rf'      tag: ")[^"]+(")'
                rf'(?:\n      digest: "sha256:[0-9a-fA-F]{{64}}")?'
            )
            replacement = rf"\g<1>{tag}\g<2>" + f'\n      digest: "{digest}"'
            text, count = re.subn(pattern, replacement, text)
            if count == 0:
                entry_pattern = rf"(?m)^  {re.escape(service)}:\s*$"
                if re.search(entry_pattern, text):
                    raise SystemExit(f"malformed image override for existing service {service}")
                header = "components:\n"
                if text.count(header) != 1:
                    raise SystemExit("expected exactly one components mapping")
                block = (
                    f"  {service}:\n"
                    "    imageOverride:\n"
                    f'      tag: "{tag}"\n'
                    f'      digest: "{digest}"\n'
                )
                text = text.replace(header, header + block, 1)
            elif count != 1:
                raise SystemExit(f"expected at most one image override for {service}, found {count}")
        path.write_text(text)

    if chart_changed:
        path = gitops_dir / APPLICATIONS
        text = path.read_text()
        pattern = (
            rf"(repoURL: '{re.escape(CHART_REPOSITORY)}'\n"
            r"      targetRevision: )[0-9a-f]{40}"
        )
        text, count = re.subn(pattern, rf"\g<1>{source_sha}", text)
        if count != 2:
            raise SystemExit(f"expected two chart source revisions, found {count}")
        path.write_text(text)


def self_test():
    old_digest = "sha256:" + "a" * 64
    new_digest = "sha256:" + "b" * 64
    chart_sha = "c" * 40
    image_revisions = f'''components:
  cart:
    imageOverride:
      tag: "old-cart"
      digest: "{old_digest}"
  payment:
    imageOverride:
      tag: "old-payment"
      digest: "{old_digest}"
'''
    applications = "\n".join(
        f"repoURL: '{CHART_REPOSITORY}'\n      targetRevision: {'d' * 40}"
        for _ in range(2)
    ) + "\n"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / IMAGE_REVISIONS).parent.mkdir(parents=True)
        (root / APPLICATIONS).parent.mkdir(parents=True)
        (root / IMAGE_REVISIONS).write_text(image_revisions)
        (root / APPLICATIONS).write_text(applications)

        update_revisions(root, ["cart"], {"cart": new_digest}, "first", "e" * 40, False)
        update_revisions(root, ["payment"], {"payment": new_digest}, "second", chart_sha, True)

        updated_images = (root / IMAGE_REVISIONS).read_text()
        updated_apps = (root / APPLICATIONS).read_text()
        assert 'tag: "first-cart"' in updated_images
        assert 'tag: "second-payment"' in updated_images
        assert updated_images.count(new_digest) == 2
        assert updated_apps.count(chart_sha) == 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gitops-dir")
    parser.add_argument("--services-json")
    parser.add_argument("--image-digests-json")
    parser.add_argument("--image-tag")
    parser.add_argument("--source-sha")
    parser.add_argument("--chart-changed", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        required = [args.gitops_dir, args.services_json, args.image_digests_json, args.image_tag, args.source_sha]
        if not all(required):
            parser.error("promotion arguments are required unless --self-test is used")
        update_revisions(
            args.gitops_dir,
            json.loads(args.services_json),
            json.loads(args.image_digests_json),
            args.image_tag,
            args.source_sha,
            args.chart_changed,
        )
