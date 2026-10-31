"""opentrust — a decentralized trust network for open source contributions."""

from .campaign import Campaign, detect_campaigns
from .eigentrust import personal_trust
from .graph import TrustGraph, from_network
from .policy import Policy
from .records import (
    build_campaign_alert,
    build_denounce,
    build_policy,
    build_retract,
    build_trust_edge,
    build_vouch,
)
from .reputation import SubjectScore, score_subject
from .signals import PR
from .store import Network, Store, load_network, load_project

__version__ = "0.1.0"

__all__ = [
    "Campaign",
    "Network",
    "PR",
    "Policy",
    "Store",
    "SubjectScore",
    "TrustGraph",
    "build_campaign_alert",
    "build_denounce",
    "build_policy",
    "build_retract",
    "build_trust_edge",
    "build_vouch",
    "detect_campaigns",
    "from_network",
    "load_network",
    "load_project",
    "personal_trust",
    "score_subject",
]
