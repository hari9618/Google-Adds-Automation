/**
 * CaughtLeads emergency pause: a Google Ads Script that runs INSIDE Google every hour, so it works
 * even when every laptop is off.
 *
 * Install (once): Google Ads > Tools > Bulk actions > Scripts > + New script. Paste this file, set
 * CONFIG below, click Authorize, then Preview (it changes nothing in Preview), then set Frequency:
 * Hourly. It only ever PAUSES; it never switches anything on or raises a budget.
 *
 * It pauses an enabled search campaign when:
 *   1. today's spend is more than PACE_FACTOR x the share of the daily budget the day has used so far
 *      (Google may spend up to 2x a daily budget on one day), once spend is above MIN_SPEND_USD; or
 *   2. its landing page does not answer 200 (an ad that sends clicks to a broken page wastes money); or
 *   3. the account's month-to-date spend is at or over MONTHLY_CAP_USD (then every campaign pauses).
 * Each pause is labelled, logged and emailed.
 */
var CONFIG = {
  EMAILS: 'you@example.com',          // comma-separated; who is told
  PACE_FACTOR: 1.5,                   // pause when spend runs 1.5x ahead of the day's pace
  MIN_SPEND_USD: 5,                   // ignore tiny early-morning amounts
  MONTHLY_CAP_USD: 0,                 // same as settings/limits.json monthly_cap_usd; 0 = not checked
  CHECK_LANDING_PAGES: true,
  LABEL: 'Paused by emergency script'
};

function main() {
  var now = new Date();
  var tz = AdsApp.currentAccount().getTimeZone();
  var hour = parseInt(Utilities.formatDate(now, tz, 'H'), 10);
  var minute = parseInt(Utilities.formatDate(now, tz, 'm'), 10);
  var dayShare = Math.max((hour + minute / 60) / 24, 1 / 24);   // at least one hour's worth
  var paused = [];

  ensureLabel(CONFIG.LABEL);

  if (CONFIG.MONTHLY_CAP_USD > 0) {
    var mtd = AdsApp.currentAccount().getStatsFor('THIS_MONTH').getCost();
    if (mtd >= CONFIG.MONTHLY_CAP_USD) {
      var all = AdsApp.campaigns().withCondition("Status = ENABLED").get();
      while (all.hasNext()) {
        var c = all.next();
        pause(c, 'month-to-date spend $' + mtd.toFixed(2) + ' reached the monthly cap $' + CONFIG.MONTHLY_CAP_USD, paused);
      }
      report(paused);
      return;
    }
  }

  var it = AdsApp.campaigns().withCondition("Status = ENABLED").get();
  while (it.hasNext()) {
    var campaign = it.next();
    var budget = campaign.getBudget().getAmount();
    var spent = campaign.getStatsFor('TODAY').getCost();
    var pace = budget * dayShare;
    if (spent >= CONFIG.MIN_SPEND_USD && spent > pace * CONFIG.PACE_FACTOR) {
      pause(campaign, 'spent $' + spent.toFixed(2) + ' by ' + hour + ':00, pace for a $' + budget.toFixed(2) +
            ' day is $' + pace.toFixed(2), paused);
      continue;
    }
    if (CONFIG.CHECK_LANDING_PAGES) {
      var broken = brokenLandingPage(campaign);
      if (broken) {
        pause(campaign, 'landing page ' + broken.url + ' answered ' + broken.code, paused);
      }
    }
  }
  report(paused);
}

function brokenLandingPage(campaign) {
  var ads = campaign.ads().withCondition("Status = ENABLED").withLimit(5).get();
  var seen = {};
  while (ads.hasNext()) {
    var urls = ads.next().urls();
    var url = urls ? urls.getFinalUrl() : null;
    if (!url || seen[url]) { continue; }
    seen[url] = true;
    try {
      var code = UrlFetchApp.fetch(url, {muteHttpExceptions: true, followRedirects: true}).getResponseCode();
      if (code !== 200) { return {url: url, code: code}; }
    } catch (e) {
      return {url: url, code: 'no answer (' + e.message + ')'};
    }
  }
  return null;
}

function pause(campaign, why, paused) {
  if (!AdsApp.getExecutionInfo().isPreview()) {
    campaign.pause();
    campaign.applyLabel(CONFIG.LABEL);
  }
  paused.push(campaign.getName() + ': ' + why);
  Logger.log('PAUSE ' + campaign.getName() + ': ' + why);
}

function ensureLabel(name) {
  if (!AdsApp.labels().withCondition("Name = '" + name + "'").get().hasNext()) {
    if (!AdsApp.getExecutionInfo().isPreview()) { AdsApp.createLabel(name); }
  }
}

function report(paused) {
  if (!paused.length) { Logger.log('All campaigns within limits.'); return; }
  var preview = AdsApp.getExecutionInfo().isPreview() ? '[PREVIEW, nothing changed] ' : '';
  MailApp.sendEmail(CONFIG.EMAILS, preview + 'CaughtLeads Ads: ' + paused.length + ' campaign(s) paused',
    'The emergency script paused:\n\n- ' + paused.join('\n- ') +
    '\n\nOpen the caughtleads-ads chat to see why and to switch them back on (that needs your Allow).');
}
