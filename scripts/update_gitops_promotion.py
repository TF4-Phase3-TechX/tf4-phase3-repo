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
KAFKA_CONNECT_SERVICE = "kafka-connect"
KAFKA_CONNECT_IRSA_ROLE_ARN = "arn:aws:iam::511825856493:role/techx-tf4-orders-kafka-connect-archive"



def update_kafka_connect_archive(path, tag, digest):
    text = path.read_text()
    block = (
        "kafkaConnectArchive:\n"
        "  enabled: true\n"
        "  image:\n"
        f'    tag: "{tag}"\n'
        f'    digest: "{digest}"\n'
        "  serviceAccount:\n"
        "    annotations:\n"
        f'      eks.amazonaws.com/role-arn: "{KAFKA_CONNECT_IRSA_ROLE_ARN}"\n'
    )
    pattern = r"(?ms)^kafkaConnectArchive:\n(?:  .*\n)*"
    text, count = re.subn(pattern, block, text)
    if count == 0:
        text = text.rstrip() + "\n" + block
    elif count != 1:
        raise SystemExit(f"expected at most one kafkaConnectArchive block, found {count}")
    path.write_text(text)

def update_revisions(gitops_dir, services, digests, image_tag, source_sha, chart_changed):
    gitops_dir = Path(gitops_dir)
    if services:
        path = gitops_dir / IMAGE_REVISIONS
        component_services = []
        if KAFKA_CONNECT_SERVICE in services:
            digest = digests.get(KAFKA_CONNECT_SERVICE)
            if not digest:
                raise SystemExit(f"missing digest for promoted service {KAFKA_CONNECT_SERVICE}")
            update_kafka_connect_archive(path, f"{image_tag}-{KAFKA_CONNECT_SERVICE}", digest)
        component_services = [service for service in services if service != KAFKA_CONNECT_SERVICE]
        text = path.read_text()
        for service in component_services:
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
        update_revisions(root, ["kafka-connect"], {"kafka-connect": new_digest}, "connect", "f" * 40, False)
        update_revisions(root, ["payment"], {"payment": new_digest}, "second", chart_sha, True)

        updated_images = (root / IMAGE_REVISIONS).read_text()
        updated_apps = (root / APPLICATIONS).read_text()
        assert 'tag: "first-cart"' in updated_images
        assert 'tag: "second-payment"' in updated_images
        assert updated_images.count(new_digest) == 3
        assert "kafkaConnectArchive:" in updated_images
        assert "enabled: true" in updated_images
        assert 'tag: "connect-kafka-connect"' in updated_images
        assert KAFKA_CONNECT_IRSA_ROLE_ARN in updated_images
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
        services = json.loads(args.services_json) if args.services_json else []
        required = [args.gitops_dir, args.services_json, args.source_sha]
        if services:
            required.extend([args.image_digests_json, args.image_tag])
        if not all(required):
            parser.error("promotion arguments are required unless --self-test is used")
        update_revisions(
            args.gitops_dir,
            services,
            json.loads(args.image_digests_json) if args.image_digests_json else {},
            args.image_tag,
            args.source_sha,
            args.chart_changed,
        )
