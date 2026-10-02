#!/usr/bin/env python3
"""Seed demo data for a clean Kompilo walkthrough.

Creates (idempotently) a demo organization + owner, a project, a few tagged prompts, and
one saved compilation (so a version exists). It talks to the RUNNING API over HTTP — no
DB internals — so it works against docker-compose or a local uvicorn alike.

Usage (with the stack running):
    cd backend && python scripts/seed_demo.py

Config via env (all optional):
    KOMPILO_API_URL        default http://localhost:8000
    KOMPILO_DEMO_ORG       default "demo"
    KOMPILO_DEMO_EMAIL     default "owner@demo.io"
    KOMPILO_DEMO_PASSWORD  default "demo-pass-1234"

Nothing here is fabricated as "real AI": the one saved compilation is produced by the real
(deterministic) Kompilo Core. Prints the credentials + what to open next.
"""

from __future__ import annotations

import os
import sys

import httpx

API = os.environ.get("KOMPILO_API_URL", "http://localhost:8000").rstrip("/")
ORG = os.environ.get("KOMPILO_DEMO_ORG", "demo")
EMAIL = os.environ.get("KOMPILO_DEMO_EMAIL", "owner@demo.io")
PASSWORD = os.environ.get("KOMPILO_DEMO_PASSWORD", "demo-pass-1234")

# (slug, name, tags) — a small, realistic library.
PROMPTS: list[tuple[str, str, list[str]]] = [
    ("welcome-email", "Email de bienvenue client", ["email", "onboarding", "demo"]),
    ("invoice-reminder", "Relance de facture impayée", ["email", "billing", "demo"]),
    ("csv-parser", "Fonction Python de parsing CSV", ["code", "python", "demo"]),
    ("release-notes", "Notes de version produit", ["writing", "product", "demo"]),
]
# The task compiled + saved as a first version of the welcome-email prompt.
SEED_TASK = "Rédige un message de bienvenue chaleureux pour un nouveau client"


def _auth(client: httpx.Client) -> str:
    """Sign up the demo org (or log in if it already exists). Returns an access token."""
    signup = client.post(
        "/v1/auth/signup",
        json={"org_slug": ORG, "org_name": "Demo", "email": EMAIL, "password": PASSWORD},
    )
    if signup.status_code in (200, 201):
        print(f"✓ created org '{ORG}' + owner {EMAIL}")
        return str(signup.json()["access_token"])
    # Already exists → log in.
    login = client.post(
        "/v1/auth/login", json={"org_slug": ORG, "email": EMAIL, "password": PASSWORD}
    )
    if login.status_code == 200:
        print(f"✓ org '{ORG}' already existed — logged in as {EMAIL}")
        return str(login.json()["access_token"])
    print(f"✗ auth failed: signup={signup.status_code} login={login.status_code}", file=sys.stderr)
    print(f"  {login.text}", file=sys.stderr)
    raise SystemExit(1)


def _ensure_project(client: httpx.Client, headers: dict[str, str]) -> str:
    created = client.post(
        "/v1/projects", headers=headers, json={"slug": "demo", "name": "Démo Kompilo"}
    )
    if created.status_code == 201:
        return str(created.json()["id"])
    # 409 → find the existing one.
    for p in client.get("/v1/projects", headers=headers).json():
        if p["slug"] == "demo":
            return str(p["id"])
    print("✗ could not create or find the demo project", file=sys.stderr)
    raise SystemExit(1)


def _ensure_prompt(
    client: httpx.Client,
    headers: dict[str, str],
    project_id: str,
    slug: str,
    name: str,
    tags: list[str],
) -> str | None:
    created = client.post(
        "/v1/prompts",
        headers=headers,
        json={"project_id": project_id, "slug": slug, "name": name, "tags": tags},
    )
    if created.status_code == 201:
        print(f"  ✓ prompt '{slug}' (tags: {', '.join(tags)})")
        return str(created.json()["id"])
    if created.status_code == 409:
        page = client.get("/v1/prompts", headers=headers, params={"q": slug}).json()
        match = next((p for p in page["items"] if p["slug"] == slug), None)
        print(f"  • prompt '{slug}' already existed")
        return str(match["id"]) if match else None
    print(f"  ✗ prompt '{slug}' failed: {created.status_code} {created.text}", file=sys.stderr)
    return None


def main() -> None:
    print(f"Seeding Kompilo demo data at {API} …")
    with httpx.Client(base_url=API, timeout=30.0) as client:
        try:
            client.get("/v1/health")
        except httpx.HTTPError:
            print(f"✗ cannot reach the API at {API}. Is the stack running?", file=sys.stderr)
            raise SystemExit(1) from None

        token = _auth(client)
        headers = {"Authorization": f"Bearer {token}"}
        project_id = _ensure_project(client, headers)
        print(f"✓ project 'demo' ({project_id})")

        first_prompt_id: str | None = None
        for slug, name, tags in PROMPTS:
            pid = _ensure_prompt(client, headers, project_id, slug, name, tags)
            if first_prompt_id is None:
                first_prompt_id = pid

        # Save one compilation so a version exists to open/diff in the demo.
        if first_prompt_id:
            save = client.post(
                f"/v1/prompts/{first_prompt_id}/compilations",
                headers=headers,
                json={"task": SEED_TASK},
            )
            if save.status_code == 201:
                v = save.json()["version"]["version"]
                print(f"✓ saved compilation v{v} on 'welcome-email'")

    print("\nDone. Sign in to the library with:")
    print(f"    org (slug): {ORG}")
    print(f"    email:      {EMAIL}")
    print(f"    password:   {PASSWORD}")
    print("\nOpen http://localhost:5173 → onglet « Bibliothèque » → connecte-toi.")


if __name__ == "__main__":
    main()
