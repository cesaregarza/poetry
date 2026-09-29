#!/usr/bin/env python3
"""Run poetry's CI checks against an existing disposable loopback PostgreSQL database."""

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-tag", default="poetry:ci-local", help="Local verification image tag"
    )
    args = parser.parse_args()
    database = os.environ.get("DATABASE_URL", "")
    if urlsplit(database).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("DATABASE_URL must name a disposable PostgreSQL database on loopback")
    if urlsplit(database).scheme not in {"postgres", "postgresql"}:
        parser.error("DATABASE_URL must use PostgreSQL")
    if not args.image_tag.strip():
        parser.error("--image-tag must not be empty")
    root = Path(__file__).resolve().parent.parent
    env = os.environ | {
        "DATABASE_SSL_REQUIRE": "false",
        "DJANGO_DEBUG": "true",
        "DJANGO_SECRET_KEY": "ci-only-not-for-runtime",
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
    }

    def run(*command, overrides=None):
        subprocess.run(command, cwd=root, env=env | (overrides or {}), check=True)

    run("uv", "sync", "--frozen")
    run("uv", "run", "ruff", "format", "--check", ".")
    run("uv", "run", "ruff", "check", ".")
    run("uv", "run", "python", "manage.py", "migrate", "--noinput")
    run("uv", "run", "python", "manage.py", "check")
    run("uv", "run", "python", "manage.py", "makemigrations", "--check", "--dry-run")
    run("uv", "run", "pytest", "-m", "not browser")
    run(
        "uv",
        "run",
        "pytest",
        "-m",
        "browser",
        "--browser",
        "chromium",
        overrides={"DJANGO_ALLOW_ASYNC_UNSAFE": "true"},
    )
    run(
        "uv",
        "run",
        "python",
        "manage.py",
        "collectstatic",
        "--noinput",
        "--clear",
        overrides={
            "DJANGO_DEBUG": "false",
            "AWS_STORAGE_BUCKET_NAME": "build-only",
            "AWS_ACCESS_KEY_ID": "build-only",
            "AWS_SECRET_ACCESS_KEY": "build-only",
            "AWS_S3_CUSTOM_DOMAIN": "build-only.invalid",
            "AWS_S3_ENDPOINT_URL": "https://build-only.invalid",
            "AWS_S3_REGION_NAME": "nyc3",
            "CLOUDFLARE_ACCESS_REQUIRED": "false",
        },
    )
    run("docker", "build", "--tag", args.image_tag, ".")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
