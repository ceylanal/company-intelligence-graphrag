# Cost Control Guide

Cloud Run staging is capped at zero minimum and one maximum instance. External database free tiers may sleep, throttle, or be deleted after inactivity; alerts and exports are the user’s responsibility. Grafana Cloud and Opik quotas must be checked in their account.

Model budgets are environment controlled. Monetary enforcement stays disabled until `config/model_pricing.yaml` contains a provider-reviewed, dated rate. Use provider hard quotas as the final safety boundary. Load tests target mock mode unless an explicit, bounded real-service test is approved.
