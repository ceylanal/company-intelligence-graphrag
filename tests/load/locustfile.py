"""Reproducible, mock-safe load scenarios selected with Locust tags."""

import os

from locust import HttpUser, between, tag, task


class HealthUser(HttpUser):
    """Public probe traffic that never invokes a paid model."""

    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        """Authenticate private Cloud Run probes without logging credentials."""
        identity_token = os.environ.get("GOOGLE_IDENTITY_TOKEN", "")
        if identity_token:
            self.client.headers.update({"Authorization": f"Bearer {identity_token}"})

    @tag("smoke", "normal")
    @task(5)
    def liveness(self) -> None:
        self.client.get("/health/live", name="/health/live")

    @tag("normal", "burst")
    @task(2)
    def version(self) -> None:
        self.client.get("/version", name="/version")

    @tag("dependency-failure")
    @task(1)
    def readiness(self) -> None:
        with self.client.get("/health/ready", name="/health/ready", catch_response=True) as response:
            if response.status_code not in (200, 503):
                response.failure(f"Unexpected readiness status {response.status_code}")

    @tag("long-running")
    @task(1)
    def repeated_probe(self) -> None:
        self.client.get("/health/live", name="/long-running-placeholder")
