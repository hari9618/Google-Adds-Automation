"""The neutral operations turn into real Google Ads API requests. Built with Google's own library
(no credentials, no network), so a renamed field in a new API version fails here, not at Allow."""

from __future__ import annotations

import pytest

pytest.importorskip("google.ads.googleads")

from google.ads.googleads.client import GoogleAdsClient
from google.auth.credentials import AnonymousCredentials

from apply.gateway import build_operations

CID = "1234567890"


@pytest.fixture(scope="module")
def client() -> GoogleAdsClient:
    return GoogleAdsClient(credentials=AnonymousCredentials(), developer_token="test", use_proto_plus=True)


def test_a_new_campaign_is_paused_search_only_and_declares_no_eu_political_ads(client):
    ops = build_operations(client, CID, {
        "op": "create_search_campaign", "name": "HVAC TX", "daily_budget_micros": 20_000_000,
        "final_url": "https://caughtleads.com/hvac", "locations": ["21176"],
        "keywords": [{"text": "hvac answering service", "match_type": "PHRASE"}],
        "negative_keywords": [{"text": "jobs", "match_type": "BROAD"}],
        "headlines": ["One", "Two", "Three"], "descriptions": ["d1", "d2"]})
    e = client.enums
    budget, campaign = ops[0].campaign_budget_operation.create, ops[1].campaign_operation.create
    assert budget.amount_micros == 20_000_000 and budget.resource_name.endswith("/campaignBudgets/-1")
    assert campaign.status == e.CampaignStatusEnum.PAUSED
    assert campaign.advertising_channel_type == e.AdvertisingChannelTypeEnum.SEARCH
    assert campaign.network_settings.target_content_network is False
    assert campaign.contains_eu_political_advertising == (
        e.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
    assert ops[2].campaign_criterion_operation.create.location.geo_target_constant == "geoTargetConstants/21176"
    assert ops[3].campaign_criterion_operation.create.negative is True
    ad = ops[-1].ad_group_ad_operation.create
    assert [h.text for h in ad.ad.responsive_search_ad.headlines] == ["One", "Two", "Three"]
    req = client.get_type("MutateGoogleAdsRequest")
    req.validate_only = True
    req.mutate_operations.extend(ops)
    assert len(req.mutate_operations) == 7


def test_a_new_ad_in_a_live_campaign_starts_switched_off(client):
    op = build_operations(client, CID, {"op": "create_rsa", "ad_group_id": "55", "final_url": "https://x.com",
                                        "headlines": ["a", "b", "c"], "descriptions": ["d", "e"]})[0]
    assert op.ad_group_ad_operation.create.status == client.enums.AdGroupAdStatusEnum.PAUSED


def test_status_and_budget_updates_carry_their_field_masks(client):
    s = build_operations(client, CID, {"op": "campaign_status", "campaign_id": "9", "status": "PAUSED"})[0]
    assert "status" in s.campaign_operation.update_mask.paths
    b = build_operations(client, CID, {"op": "budget_amount", "budget_resource": f"customers/{CID}/campaignBudgets/9",
                                       "amount_micros": 15_000_000})[0]
    assert "amount_micros" in b.campaign_budget_operation.update_mask.paths


def test_an_unknown_operation_is_refused(client):
    with pytest.raises(ValueError):
        build_operations(client, CID, {"op": "delete_everything"})
