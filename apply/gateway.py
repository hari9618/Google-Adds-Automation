"""The only code that talks to Google Ads to CHANGE something.

`Gateway` is what the Apply tool needs from Google: the current state of the campaigns, the
month-to-date cost, and one `mutate` that takes neutral operations (plain dicts) and either
test-runs them (validate_only=True: Google checks everything and changes nothing) or makes them.
`GoogleGateway` does that with Google's official library; tests use a fake with the same shape.

Neutral operations (the `op` key):
  campaign_status        campaign_id, status ("PAUSED" | "ENABLED")
  budget_amount          budget_resource, amount_micros
  campaign_negatives     campaign_id, keywords [{text, match_type}]
  remove_criteria        resource_names [...]
  create_search_campaign name, daily_budget_micros, final_url, locations [geo ids], keywords,
                         negative_keywords, headlines, descriptions
  create_rsa             ad_group_id, final_url, headlines, descriptions (always created PAUSED)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
MICROS = 1_000_000


@dataclass
class CampaignState:
    id: str
    name: str
    status: str                  # ENABLED | PAUSED | REMOVED
    budget_resource: str
    daily_budget_micros: int
    budget_shared: bool


class Gateway(Protocol):
    customer_id: str

    def campaigns(self) -> list[CampaignState]: ...

    def month_to_date_cost_micros(self) -> int: ...

    def mutate(self, ops: list[dict[str, Any]], validate_only: bool) -> list[str]: ...


class GoogleGateway:
    """Google's official `google-ads` library (API v26 at the time of writing)."""

    def __init__(self, customer_id: str, login_customer_id: str = "", yaml_path: str | None = None) -> None:
        from google.ads.googleads.client import GoogleAdsClient

        path = yaml_path or os.environ.get("CL_ADS_GOOGLE_ADS_YAML") or str(ROOT / "secrets" / "google-ads.yaml")
        self.client = GoogleAdsClient.load_from_storage(path)
        if login_customer_id:
            self.client.login_customer_id = login_customer_id
        self.customer_id = customer_id

    # ------------------------------------------------------------------ reads
    def _search(self, query: str) -> list[Any]:
        svc = self.client.get_service("GoogleAdsService")
        return list(svc.search(customer_id=self.customer_id, query=query))

    def campaigns(self) -> list[CampaignState]:
        rows = self._search(
            "SELECT campaign.id, campaign.name, campaign.status, campaign_budget.resource_name, "
            "campaign_budget.amount_micros, campaign_budget.explicitly_shared "
            "FROM campaign WHERE campaign.status != 'REMOVED'")
        return [CampaignState(str(r.campaign.id), r.campaign.name, r.campaign.status.name,
                              r.campaign_budget.resource_name, int(r.campaign_budget.amount_micros),
                              bool(r.campaign_budget.explicitly_shared)) for r in rows]

    def month_to_date_cost_micros(self) -> int:
        rows = self._search("SELECT metrics.cost_micros FROM customer WHERE segments.date DURING THIS_MONTH")
        return sum(int(r.metrics.cost_micros) for r in rows)

    # ----------------------------------------------------------------- writes
    def mutate(self, ops: list[dict[str, Any]], validate_only: bool) -> list[str]:
        client = self.client
        svc = client.get_service("GoogleAdsService")
        request = client.get_type("MutateGoogleAdsRequest")
        request.customer_id = self.customer_id
        request.validate_only = validate_only
        for op in ops:
            request.mutate_operations.extend(build_operations(client, self.customer_id, op))
        response = svc.mutate(request=request)
        names: list[str] = []
        for r in response.mutate_operation_responses:
            for field in ("campaign_result", "campaign_budget_result", "campaign_criterion_result",
                          "ad_group_result", "ad_group_criterion_result", "ad_group_ad_result"):
                if r._pb.HasField(field):
                    names.append(getattr(r, field).resource_name)
        return names


def build_operations(client: Any, customer_id: str, op: dict[str, Any]) -> list[Any]:
    """Neutral operation -> Google MutateOperations. Separate from the gateway so it can be tested
    against the real library's types without credentials or network."""
    from google.api_core import protobuf_helpers

    cid = customer_id
    enums = client.enums
    paths = client.get_service("GoogleAdsService")
    out: list[Any] = []

    def mop() -> Any:
        m = client.get_type("MutateOperation")
        out.append(m)
        return m

    kind = op["op"]
    if kind == "campaign_status":
        m = mop()
        c = m.campaign_operation.update
        c.resource_name = paths.campaign_path(cid, op["campaign_id"])
        c.status = getattr(enums.CampaignStatusEnum, op["status"])
        client.copy_from(m.campaign_operation.update_mask, protobuf_helpers.field_mask(None, c._pb))
    elif kind == "budget_amount":
        m = mop()
        b = m.campaign_budget_operation.update
        b.resource_name = op["budget_resource"]
        b.amount_micros = int(op["amount_micros"])
        client.copy_from(m.campaign_budget_operation.update_mask, protobuf_helpers.field_mask(None, b._pb))
    elif kind == "campaign_negatives":
        for kw in op["keywords"]:
            m = mop()
            cc = m.campaign_criterion_operation.create
            cc.campaign = paths.campaign_path(cid, op["campaign_id"])
            cc.negative = True
            cc.keyword.text = kw["text"]
            cc.keyword.match_type = getattr(enums.KeywordMatchTypeEnum, kw["match_type"])
    elif kind == "remove_criteria":
        for rn in op["resource_names"]:
            m = mop()
            if "/campaignCriteria/" in rn:
                m.campaign_criterion_operation.remove = rn
            else:
                m.ad_group_criterion_operation.remove = rn
    elif kind == "create_search_campaign":
        budget_rn = paths.campaign_budget_path(cid, "-1")
        campaign_rn = paths.campaign_path(cid, "-2")
        ad_group_rn = paths.ad_group_path(cid, "-3")
        m = mop()
        b = m.campaign_budget_operation.create
        b.resource_name = budget_rn
        b.name = f"{op['name']} budget"
        b.amount_micros = int(op["daily_budget_micros"])
        b.delivery_method = enums.BudgetDeliveryMethodEnum.STANDARD
        b.explicitly_shared = False
        m = mop()
        c = m.campaign_operation.create
        c.resource_name = campaign_rn
        c.name = op["name"]
        c.status = enums.CampaignStatusEnum.PAUSED          # every new campaign starts switched off
        c.advertising_channel_type = enums.AdvertisingChannelTypeEnum.SEARCH
        c.campaign_budget = budget_rn
        client.copy_from(c.maximize_conversions, client.get_type("MaximizeConversions"))
        c.network_settings.target_google_search = True
        c.network_settings.target_search_network = False
        c.network_settings.target_content_network = False
        c.network_settings.target_partner_search_network = False
        c.geo_target_type_setting.positive_geo_target_type = (
            enums.PositiveGeoTargetTypeEnum.PRESENCE)         # people IN the area, not interested in it
        c.contains_eu_political_advertising = (
            enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
        for geo in op.get("locations", []):
            m = mop()
            cc = m.campaign_criterion_operation.create
            cc.campaign = campaign_rn
            cc.location.geo_target_constant = f"geoTargetConstants/{geo}"
        for kw in op.get("negative_keywords", []):
            m = mop()
            cc = m.campaign_criterion_operation.create
            cc.campaign = campaign_rn
            cc.negative = True
            cc.keyword.text = kw["text"]
            cc.keyword.match_type = getattr(enums.KeywordMatchTypeEnum, kw["match_type"])
        m = mop()
        ag = m.ad_group_operation.create
        ag.resource_name = ad_group_rn
        ag.name = f"{op['name']} ad group"
        ag.campaign = campaign_rn
        ag.status = enums.AdGroupStatusEnum.ENABLED
        ag.type_ = enums.AdGroupTypeEnum.SEARCH_STANDARD
        for kw in op.get("keywords", []):
            m = mop()
            k = m.ad_group_criterion_operation.create
            k.ad_group = ad_group_rn
            k.status = enums.AdGroupCriterionStatusEnum.ENABLED
            k.keyword.text = kw["text"]
            k.keyword.match_type = getattr(enums.KeywordMatchTypeEnum, kw["match_type"])
        _rsa(client, mop(), ad_group_rn, op, enums.AdGroupAdStatusEnum.ENABLED)
    elif kind == "create_rsa":
        _rsa(client, mop(), paths.ad_group_path(cid, op["ad_group_id"]), op,
             enums.AdGroupAdStatusEnum.PAUSED)                # a new ad in a live campaign starts off
    else:
        raise ValueError(f"unknown operation {kind!r}")
    return out


def _rsa(client: Any, m: Any, ad_group_rn: str, op: dict[str, Any], status: Any) -> None:
    ada = m.ad_group_ad_operation.create
    ada.ad_group = ad_group_rn
    ada.status = status
    ada.ad.final_urls.append(op["final_url"])
    for text in op["headlines"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ada.ad.responsive_search_ad.headlines.append(asset)
    for text in op["descriptions"]:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        ada.ad.responsive_search_ad.descriptions.append(asset)
