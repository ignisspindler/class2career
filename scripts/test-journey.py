#!/usr/bin/env python3
"""
test-journey.py — Full customer journey test
Tests every step of the funnel against a locally running Flask server.

Usage:
  bash scripts/run-local.sh            # terminal 1
  python3 scripts/test-journey.py      # terminal 2

Options (env vars):
  BASE_URL    defaults to http://localhost:5000
  TEST_EMAIL  defaults to test+journey@example.com
  COHORT      defaults to class2careers
  CRON_SECRET must match the value in .env
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error

BASE_URL    = os.environ.get('BASE_URL',    'http://localhost:5000')
TEST_EMAIL  = os.environ.get('TEST_EMAIL',  'test+journey@example.com')
COHORT      = os.environ.get('COHORT',      'class2careers')
CRON_SECRET = os.environ.get('CRON_SECRET', '')

PASS = '\033[92m  PASS\033[0m'
FAIL = '\033[91m  FAIL\033[0m'
INFO = '\033[94m  INFO\033[0m'
WARN = '\033[93m  WARN\033[0m'

results = []


# ─── HTTP helpers ───────────────────────────────────────────────────────────────

def get(path, headers=None):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            return r.status, r.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()

def post_form(path, fields):
    data = urllib.parse.urlencode(fields).encode()
    req  = urllib.request.Request(f"{BASE_URL}{path}", data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            return r.status, r.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()

def post_json(path, payload, headers=None, timeout=10):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(f"{BASE_URL}{path}", data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, r.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


def check(label, cond, detail=''):
    ok = bool(cond)
    tag = PASS if ok else FAIL
    print(f"{tag}  {label}" + (f"  [{detail}]" if detail else ''))
    results.append((label, ok))
    return ok


# ─── Tests ─────────────────────────────────────────────────────────────────────

def test_server_reachable():
    print("\n── 0. Server health ──────────────────────────────────────────────────")
    status, _, body = get('/')
    if status == 0:
        print(f"{FAIL}  Cannot reach {BASE_URL} — is the server running?")
        print(f"       Run:  bash scripts/run-local.sh")
        sys.exit(1)
    print(f"{INFO}  Server responded with HTTP {status}")


def test_subscribe():
    print("\n── 1. Subscribe (lead capture + email 1) ─────────────────────────────")
    status, headers, body = post_form('/subscribe', {
        'email':      TEST_EMAIL,
        'cohort':     COHORT,
        'lead_magnet': 'interview-guide-test',
        'utm_source': COHORT,
    })
    check("HTTP 200", status == 200, f"got {status}")

    try:
        data = json.loads(body)
    except Exception:
        check("Response is JSON", False, body[:120].decode(errors='replace'))
        return None

    check("success=true",  data.get('success') is True)
    check("email_sent",    data.get('email_sent') is True,
          "SendGrid delivered seq-1 email" if data.get('email_sent') else
          "SendGrid returned false (check key / quota)")
    print(f"{INFO}  message: {data.get('message', '')}")
    return data


def test_download_lead(download_url):
    print("\n── 2. Lead magnet PDF download ───────────────────────────────────────")
    if not download_url:
        print(f"{WARN}  No download URL available — skipping.")
        return

    # Verify the /download endpoint (token should already be in Redis from subscribe)
    status, headers, body = get(download_url.replace(BASE_URL, ''))
    ct = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''
    check("HTTP 200",           status == 200,  f"got {status}")
    check("Content-Type PDF",   'pdf' in ct.lower(),
          f"Content-Type: {ct}" if ct else "no Content-Type header")
    check("Non-empty body",     len(body) > 10_000,
          f"{len(body):,} bytes — expected >10KB for a real PDF")


def test_stats_json():
    print("\n── 3. Stats endpoint (JSON) ───────────────────────────────────────────")
    status, headers, body = get('/stats')
    check("HTTP 200", status == 200, f"got {status}")
    try:
        data = json.loads(body)
    except Exception:
        check("Response is JSON", False, body[:80].decode(errors='replace'))
        return None
    check("leads_total >= 1",   data.get('leads_total', 0) >= 1,
          str(data.get('leads_total')))
    check("by_cohort present",  bool(data.get('by_cohort')))
    check("sequence_sends present", 'sequence_sends' in data)
    print(f"{INFO}  leads={data.get('leads_total')}  "
          f"purchases={data.get('purchases_total')}  "
          f"conv={data.get('conversion_rate')}%")
    return data


def test_stats_html():
    print("\n── 4. Stats dashboard (HTML browser view) ────────────────────────────")
    status, headers, body = get('/stats', headers={'Accept': 'text/html'})
    check("HTTP 200", status == 200, f"got {status}")
    html = body.decode(errors='replace')
    check("Renders HTML", '<html' in html.lower())
    check("Shows leads count", 'Total Leads' in html)
    check("Shows cohort table", 'By Cohort' in html)
    check("Shows sequence table", 'Sequence Emails' in html)
    print(f"{INFO}  Open {BASE_URL}/stats in your browser for the live dashboard.")


def test_cron():
    print("\n── 5. Cron worker ────────────────────────────────────────────────────")
    headers = {}
    if CRON_SECRET:
        headers['Authorization'] = f'Bearer {CRON_SECRET}'
    print(f"{INFO}  Sending cron request (may take 30-60s for large lead lists)...")
    status, _, body = post_json('/cron/send-sequence', {}, headers=headers, timeout=120)
    check("HTTP 200 or 401", status in [200, 401], f"got {status}")
    if status == 401 and not CRON_SECRET:
        print(f"{WARN}  Cron returned 401 — set CRON_SECRET env var to match .env")
        return
    if status == 200:
        try:
            data = json.loads(body)
        except Exception:
            check("Response is JSON", False)
            return
        check("leads_checked >= 1",  data.get('leads_checked', 0) >= 1,
              str(data.get('leads_checked')))
        print(f"{INFO}  sent={data.get('sent')}  skipped={data.get('skipped')}  "
              f"errors={data.get('errors')}")
        print(f"{INFO}  No emails sent yet (test lead subscribed <7 days ago). Expected.")


def test_stripe_purchase():
    print("\n── 6. Stripe purchase simulation ─────────────────────────────────────")
    status, _, body = post_json('/webhook/stripe/test', {
        'email':  TEST_EMAIL,
        'cohort': COHORT,
    })
    if status == 404:
        print(f"{WARN}  /webhook/stripe/test returned 404 — "
              "server must run with FLASK_ENV=development")
        return None
    check("HTTP 200", status == 200, f"got {status}")
    try:
        data = json.loads(body)
    except Exception:
        check("Response is JSON", False, body[:80].decode(errors='replace'))
        return None
    check("success=true",  data.get('success') is True)
    check("token present", bool(data.get('token')))
    check("access_url",    bool(data.get('access_url')))
    check("email_sent",    data.get('email_sent') is True,
          "purchase thank-you email delivered" if data.get('email_sent') else
          "SendGrid returned false")
    print(f"{INFO}  token:      {data.get('token', '')[:20]}...")
    print(f"{INFO}  access_url: {data.get('access_url', '')}")
    return data


def test_access_page(token):
    print("\n── 7. Access page (purchase token gate) ──────────────────────────────")
    if not token:
        print(f"{WARN}  No purchase token — skipping.")
        return

    # Valid token
    status, headers, body = get(f'/access?token={token}',
                                 headers={'Accept': 'text/html'})
    html = body.decode(errors='replace')
    check("HTTP 200",              status == 200,  f"got {status}")
    check("Shows Your Toolkit",    "Your Toolkit" in html or "toolkit" in html.lower())
    check("Download links present", '/download?' in html)
    check("Links use purchase token", token[:12] in html)

    # Missing token
    status2, _, _ = get('/access')
    check("Missing token → 403",   status2 == 403, f"got {status2}")

    # Bogus token
    status3, _, _ = get('/access?token=invalid-bogus-token')
    check("Invalid token → 403",   status3 == 403, f"got {status3}")


def test_workbook_downloads(token):
    print("\n── 8. Workbook downloads (secure) ────────────────────────────────────")
    if not token:
        print(f"{WARN}  No purchase token — skipping.")
        return

    workbooks = ['wb01', 'wb02', 'wb03', 'wb04', 'wb05', 'journal']
    for key in workbooks:
        status, headers, body = get(f'/download?token={token}&file={key}')
        ct = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''
        ok = status == 200 and len(body) > 1000
        check(f"  {key}: HTTP 200 + content",  ok,
              f"status={status}  bytes={len(body):,}  ct={ct}")

    # Unauthorized attempt (no token)
    status_bad, _, _ = get(f'/download?token=bad&file=wb01')
    check("Bad token → 403",  status_bad == 403, f"got {status_bad}")


def test_direct_pdf_blocked():
    print("\n── 9. Direct PDF URL blocked (Vercel routing only) ───────────────────")
    pdf_name = f"interview-mastery-{COHORT}.pdf"
    status, _, _ = get(f"/lead_magnets/{pdf_name}")
    # Locally Flask returns 404 (no matching route); on Vercel the route rule returns 403.
    # Both mean the file is not served — either is acceptable locally.
    blocked = status in [403, 404]
    check("Direct /lead_magnets/*.pdf not served",  blocked,
          f"got {status}" + (" (404 locally = OK; 403 on Vercel)" if status == 404 else ""))


def test_cron_forces_seq2(stats_before):
    """
    Fast-forward a lead's subscribed_at timestamp so the cron sends email 2,
    then restore it afterward.
    """
    print("\n── 10. Force seq-2 send via cron (backdating subscribe timestamp) ──")

    # We need direct Redis access for this. Load .env to get creds.
    site_dir = os.path.join(os.path.dirname(__file__), '..')
    env_file = os.path.join(site_dir, '.env')
    upstash_url = os.environ.get('UPSTASH_REDIS_REST_URL', '')
    upstash_tok = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')

    if not upstash_url or not upstash_tok:
        # Try loading from .env
        if os.path.isfile(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or '=' not in line:
                        continue
                    k, _, v = line.partition('=')
                    if k == 'UPSTASH_REDIS_REST_URL':
                        upstash_url = v.strip()
                    if k == 'UPSTASH_REDIS_REST_TOKEN':
                        upstash_tok = v.strip()

    if not upstash_url:
        print(f"{WARN}  UPSTASH_REDIS_REST_URL not set — cannot backdate for cron test. Skipping.")
        return

    def redis_cmd(*cmd):
        payload = json.dumps([list(cmd)]).encode()
        req = urllib.request.Request(f"{upstash_url}/pipeline", data=payload, method='POST')
        req.add_header('Authorization', f'Bearer {upstash_tok}')
        req.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())[0].get('result')
        except Exception as e:
            print(f"        Redis error: {e}")
            return None

    # Remove seq:sent:2 so the cron thinks it's not been sent
    redis_cmd('SREM', f'seq:sent:{TEST_EMAIL}', '2')

    # Backdate subscribed_at by 8 days so email 2 is due
    eight_days_ago = int(time.time()) - (8 * 86400)
    redis_cmd('SET', f'seq:subscribed_at:{TEST_EMAIL}', json.dumps(eight_days_ago))

    # Remove both the seq:sent 'purchased' flag AND the purchase:{email} key
    # (the cron's has_purchased() checks the purchase: key, not the seq:sent set)
    redis_cmd('SREM', f'seq:sent:{TEST_EMAIL}', 'purchased')
    purchase_backup = redis_cmd('GET', f'purchase:{TEST_EMAIL}')
    redis_cmd('DEL', f'purchase:{TEST_EMAIL}')

    print(f"{INFO}  Backdated subscribed_at to 8 days ago. Running cron (may take 30-60s)...")

    headers = {}
    if CRON_SECRET:
        headers['Authorization'] = f'Bearer {CRON_SECRET}'
    status, _, body = post_json('/cron/send-sequence', {}, headers=headers, timeout=120)
    check("Cron HTTP 200", status == 200, f"got {status}")

    if status == 200:
        data = json.loads(body)
        check("Sent count >= 1",  data.get('sent', 0) >= 1,
              f"sent={data.get('sent')}  — check SendGrid inbox for seq-2 email")
        print(f"{INFO}  {data}")

    # Restore purchase key and mark all seq emails done
    if purchase_backup:
        redis_cmd('SET', f'purchase:{TEST_EMAIL}', purchase_backup)
    for n in range(1, 7):
        redis_cmd('SADD', f'seq:sent:{TEST_EMAIL}', str(n))
    redis_cmd('SADD', f'seq:sent:{TEST_EMAIL}', 'purchased')
    print(f"{INFO}  Restored test lead to purchased state.")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Class2Career — Full Customer Journey Test")
    print(f"  BASE_URL   : {BASE_URL}")
    print(f"  TEST_EMAIL : {TEST_EMAIL}")
    print(f"  COHORT     : {COHORT}")
    print("=" * 62)

    test_server_reachable()

    # 1. Subscribe
    sub_data = test_subscribe()

    # Figure out the download URL from the subscribe result or construct it
    # (the actual token is in Redis; for the test we just call /download directly
    #  after subscribe — the server gave us no token in the response by design)
    # We'll test the download endpoint indirectly via test_stripe_purchase's access page.
    # For the lead magnet test, we need to pull the token from Redis.
    download_url = None
    # (Covered in test_stripe_purchase + test_access_page instead)

    # 2. Stats checks
    stats_before = test_stats_json()
    test_stats_html()

    # 3. Cron (no-op, lead just subscribed)
    test_cron()

    # 4. Simulate Stripe purchase
    purchase_data = test_stripe_purchase()
    token = purchase_data.get('token') if purchase_data else None

    # 5. Access page
    test_access_page(token)

    # 6. Workbook downloads
    test_workbook_downloads(token)

    # 7. Direct PDF access blocked
    test_direct_pdf_blocked()

    # 8. Force seq-2 send (backdates Redis timestamp)
    test_cron_forces_seq2(stats_before)

    # ── Final stats ────────────────────────────────────────────────────────────
    print("\n── Final stats ───────────────────────────────────────────────────────")
    test_stats_json()

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print(f"  Results: {passed} passed  {failed} failed  ({len(results)} total)")
    if failed:
        print(f"\033[91m  Failed checks:\033[0m")
        for label, ok in results:
            if not ok:
                print(f"    - {label}")
    else:
        print(f"\033[92m  All checks passed.\033[0m")
    print("=" * 62)
    print(f"\n  Dashboard: {BASE_URL}/stats  (open in browser)")
    print()


if __name__ == '__main__':
    main()
