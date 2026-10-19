import email.message
import hashlib
import io
import json
import os
import socket
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock

import net

URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


class FakeResp:
    def __init__(self, status, body):
        self.status = status
        self.headers = email.message.Message()
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(obj):
    return FakeResp(200, json.dumps(obj))


def http_error(code, body="", headers=None, url=URL):
    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError(url, code, "status %d" % code, msg, io.BytesIO(body.encode()))


class FakeOpen:
    """Stands in for urllib.request.urlopen: returns or raises the queued outcomes in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append((req, timeout))
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def no_network(*args, **kwargs):
    raise AssertionError("network touched")


class NetTestCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("JOB_SCOUT_REPLAY_DIR", None)
        os.environ.pop("JOB_SCOUT_RECORD_DIR", None)
        sleep = mock.patch.object(net, "_sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def opener(self, *outcomes):
        fake = FakeOpen(*outcomes)
        p = mock.patch.object(net, "_urlopen", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake


class ConstantsTest(unittest.TestCase):
    def test_version_and_user_agent(self):
        path = os.path.join(os.path.dirname(net.__file__), os.pardir, "VERSION")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(net.VERSION, f.read().strip())
        self.assertEqual(net.USER_AGENT, "job-scout/%s (+https://github.com/sorawit-w/job-scout)" % net.VERSION)
        self.assertEqual((net.TIMEOUT, net.MAX_WORKERS), (20, 8))

    def test_fixture_key(self):
        self.assertEqual(net.fixture_key(URL), hashlib.sha1(URL.encode()).hexdigest()[:16])


class GetJsonTest(NetTestCase):
    def test_sends_user_agent_accept_and_timeout(self):
        fake = self.opener(ok({}))
        net.get_json(URL)
        req, timeout = fake.calls[0]
        self.assertEqual(req.get_header("User-agent"), net.USER_AGENT)
        self.assertEqual(req.get_header("Accept"), "application/json")
        self.assertEqual(timeout, 20)

    def test_200_returns_parsed_json(self):
        self.opener(ok({"jobs": [1, 2]}))
        self.assertEqual(net.get_json(URL), {"jobs": [1, 2]})

    def test_404_and_410_return_none(self):
        self.opener(http_error(404), http_error(410))
        self.assertIsNone(net.get_json(URL))
        self.assertIsNone(net.get_json(URL))

    def test_429_then_200_sleeps_retry_after_capped_at_10(self):
        fake = self.opener(http_error(429, headers={"Retry-After": "30"}), ok({"a": 1}))
        self.assertEqual(net.get_json(URL), {"a": 1})
        self.sleep.assert_called_once_with(10.0)
        self.assertEqual(len(fake.calls), 2)

    def test_retry_after_below_cap_and_default(self):
        self.opener(http_error(503, headers={"Retry-After": "3"}), ok({}), http_error(502), ok({}))
        net.get_json(URL)
        net.get_json(URL)
        self.assertEqual(self.sleep.call_args_list, [mock.call(3.0), mock.call(2.0)])

    def test_500_twice_raises_after_two_attempts(self):
        fake = self.opener(http_error(500), http_error(500))
        with self.assertRaises(net.HTTPStatusError) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(len(fake.calls), 2)

    def test_timeout_twice_is_blocked_timeout(self):
        fake = self.opener(socket.timeout("t"), urllib.error.URLError(socket.timeout("t")))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "timeout")
        self.assertEqual(len(fake.calls), 2)

    def test_timeout_then_200_recovers(self):
        self.opener(socket.timeout("t"), ok({"a": 1}))
        self.assertEqual(net.get_json(URL), {"a": 1})

    def test_dns_failure(self):
        fake = self.opener(urllib.error.URLError(socket.gaierror(8, "nodename nor servname")))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "dns")
        self.assertEqual(len(fake.calls), 1)

    def test_tls_failure(self):
        self.opener(urllib.error.URLError(ssl.SSLError(1, "CERTIFICATE_VERIFY_FAILED")))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "tls")

    def test_connection_refused_is_network(self):
        self.opener(urllib.error.URLError(ConnectionRefusedError(61, "refused")))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "network")

    def test_403_with_via_header_is_proxy_block(self):
        self.opener(http_error(403, headers={"Via": "1.1 egress-proxy"}))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "proxy_403")

    def test_403_with_allowlist_body_is_proxy_block(self):
        self.opener(http_error(403, body="Host not in allowlist"))
        with self.assertRaises(net.Blocked) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "proxy_403")

    def test_plain_403_is_status_error(self):
        self.opener(http_error(403, body="Forbidden"))
        with self.assertRaises(net.HTTPStatusError) as ctx:
            net.get_json(URL)
        self.assertEqual(ctx.exception.status, 403)

    def test_invalid_json_is_net_error(self):
        self.opener(FakeResp(200, "<html>"))
        with self.assertRaises(net.NetError) as ctx:
            net.get_json(URL)
        self.assertNotIsInstance(ctx.exception, net.HTTPStatusError)
        self.assertIn(URL, str(ctx.exception))


class BudgetTest(NetTestCase):
    def test_third_call_exceeds_budget_of_two(self):
        fake = self.opener(ok({}), ok({}), ok({}))
        budget = net.Budget(2)
        net.get_json(URL, budget)
        net.get_json(URL, budget)
        with self.assertRaises(net.BudgetExceeded):
            net.get_json(URL, budget)
        self.assertEqual((budget.cap, budget.used, len(fake.calls)), (2, 2, 2))

    def test_retry_attempt_is_counted(self):
        self.opener(http_error(429), ok({}))
        budget = net.Budget(5)
        net.get_json(URL, budget)
        self.assertEqual(budget.used, 2)

    def test_none_cap_is_unlimited(self):
        budget = net.Budget(None)
        for _ in range(100):
            budget.take()
        self.assertEqual(budget.used, 100)


class ReplayRecordTest(NetTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def test_replay_hit_200_and_404_without_network(self):
        other = URL + "/999"
        net.write_fixture(self.dir, URL, 200, json.dumps({"jobs": []}))
        net.write_fixture(self.dir, other, 404, None)
        budget = net.Budget(10)
        with mock.patch.object(net, "_urlopen", no_network), \
                mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": self.dir}):
            self.assertEqual(net.get_json(URL, budget), {"jobs": []})
            self.assertIsNone(net.get_json(other, budget))
        self.assertEqual(budget.used, 2)

    def test_replay_500_raises_without_sleep(self):
        net.write_fixture(self.dir, URL, 500, "")
        with mock.patch.object(net, "_urlopen", no_network), \
                mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": self.dir}):
            with self.assertRaises(net.HTTPStatusError):
                net.get_json(URL)
        self.sleep.assert_not_called()

    def test_replay_miss_is_blocked(self):
        with mock.patch.object(net, "_urlopen", no_network), \
                mock.patch.dict(os.environ, {"JOB_SCOUT_REPLAY_DIR": self.dir}):
            with self.assertRaises(net.Blocked) as ctx:
                net.get_json(URL)
        self.assertEqual(ctx.exception.hint, "replay_miss")
        self.assertIn(URL, str(ctx.exception))

    def test_record_writes_fixture(self):
        rec = os.path.join(self.dir, "new")
        self.opener(ok({"a": 1}), http_error(404, body="nope"))
        with mock.patch.dict(os.environ, {"JOB_SCOUT_RECORD_DIR": rec}):
            net.get_json(URL)
            net.get_json(URL + "/1")
        with open(os.path.join(rec, net.fixture_key(URL) + ".json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"url": URL, "status": 200, "body": '{"a": 1}'})
        with open(os.path.join(rec, net.fixture_key(URL + "/1") + ".json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["status"], 404)

    def test_record_skips_network_exceptions(self):
        self.opener(urllib.error.URLError(socket.gaierror(8, "x")))
        with mock.patch.dict(os.environ, {"JOB_SCOUT_RECORD_DIR": self.dir}):
            with self.assertRaises(net.Blocked):
                net.get_json(URL)
        self.assertEqual(os.listdir(self.dir), [])


class HealthTest(NetTestCase):
    def patch_by_host(self, blocked_host=None, error=None):
        def fake(req, timeout=None):
            self.calls.append(req.full_url)
            if blocked_host and blocked_host in req.full_url:
                raise error
            raise http_error(404, url=req.full_url)
        self.calls = []
        p = mock.patch.object(net, "_urlopen", fake)
        p.start()
        self.addCleanup(p.stop)

    def test_all_hosts_reachable_via_404(self):
        self.patch_by_host()
        result = net.health()
        self.assertEqual(result, {"ok": True, "hosts": {h: "ok" for h in net.HEALTH_URLS}, "hint": None})
        self.assertEqual(len(self.calls), 3)

    def test_one_host_dns_failure(self):
        self.patch_by_host("api.lever.co", urllib.error.URLError(socket.gaierror(8, "x")))
        result = net.health()
        self.assertFalse(result["ok"])
        self.assertEqual(result["hosts"]["api.lever.co"], "blocked: dns")
        self.assertEqual(result["hosts"]["api.ashbyhq.com"], "ok")
        self.assertEqual(result["hint"], "dns")

    def test_timeout_is_not_retried(self):
        self.patch_by_host("api.ashbyhq.com", socket.timeout("t"))
        result = net.health()
        self.assertEqual(result["hosts"]["api.ashbyhq.com"], "blocked: timeout")
        self.assertEqual(len(self.calls), 3)

    def test_proxy_403_counts_as_blocked(self):
        self.patch_by_host("greenhouse", http_error(403, headers={"Proxy-Agent": "squid"}))
        result = net.health()
        self.assertEqual(result["hosts"]["boards-api.greenhouse.io"], "blocked: proxy_403")
        self.assertEqual(result["hint"], "proxy_403")


if __name__ == "__main__":
    unittest.main()
