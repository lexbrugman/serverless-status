"""Step zero's reading of the plan: which account owns which check.

The failure this guards against is quiet. Asking one tenant about another
tenant's jobs returns nothing, and nothing is indistinguishable from a probe
that never ran — so a working bootstrap fails after twelve minutes saying
the checks are not publishing.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "ci_verify_step_zero", ROOT / "template" / "bin" / "ci-verify-step-zero.py"
)
step_zero = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step_zero)


def stack(account, host, user):
    return {
        "address": f"module.{account}.data.grafana_cloud_stack.this",
        "type": "grafana_cloud_stack",
        "mode": "data",
        "values": {"prometheus_url": host, "prometheus_user_id": user},
    }


def token(account, secret):
    return {
        "address": f"module.{account}.grafana_cloud_access_policy_token.metrics_read",
        "type": "grafana_cloud_access_policy_token",
        "name": "metrics_read",
        "values": {"token": secret},
    }


def smtp_check(account, job):
    return {
        "address": f'module.{account}.grafana_synthetic_monitoring_check.smtp["{job}"]',
        "type": "grafana_synthetic_monitoring_check",
        "values": {
            "job": job,
            "settings": [{"tcp": [{"query_response": [{"expect": "^220", "send": "Ehlo x"}]}]}],
        },
    }


TWO_ACCOUNTS = [
    stack("checks_one", "https://prom-one.example", 111),
    token("checks_one", "token-one"),
    smtp_check("checks_one", "mx-one-smtp"),
    stack("checks_two", "https://prom-two.example", 222),
    token("checks_two", "token-two"),
    smtp_check("checks_two", "mx-two-smtp"),
]


class TestAccountOf:
    def test_it_reads_the_module_path(self):
        assert step_zero.account_of("module.checks_one.data.x.y") == "module.checks_one"
        assert step_zero.account_of("module.a.module.b.x.y") == "module.a.module.b"

    def test_a_root_resource_belongs_to_no_account(self):
        assert step_zero.account_of("grafana_synthetic_monitoring_installation.one") == ""


class TestCredentials:
    def test_each_account_keeps_its_own(self):
        found = step_zero.prometheus_credentials(TWO_ACCOUNTS)
        assert set(found) == {"module.checks_one", "module.checks_two"}
        assert found["module.checks_one"]["token"] == "token-one"
        assert found["module.checks_two"]["user"] == "222"
        assert found["module.checks_two"]["query_url"] == "https://prom-two.example/api/prom"

    def test_an_incomplete_account_is_not_offered(self):
        """Half a credential cannot query anything, and reporting it as
        usable turns a missing token into a probe that never ran."""
        assert step_zero.prometheus_credentials([stack("checks_one", "https://p", 1)]) == {}


class TestDialogues:
    def test_every_check_carries_the_account_it_publishes_to(self):
        state = step_zero.state_dialogues(TWO_ACCOUNTS)
        assert state["mx-one-smtp"]["account"] == "module.checks_one"
        assert state["mx-two-smtp"]["account"] == "module.checks_two"

    def test_the_dialogue_survives_the_grouping(self):
        state = step_zero.state_dialogues(TWO_ACCOUNTS)
        assert state["mx-one-smtp"]["entries"] == [
            {"expect": "^220", "send": "Ehlo x", "start_tls": False}
        ]

    def test_no_account_queries_another_accounts_jobs(self):
        """The bug this file exists for: one account's credentials awaiting
        every account's checks."""
        state = step_zero.state_dialogues(TWO_ACCOUNTS)
        credentials = step_zero.prometheus_credentials(TWO_ACCOUNTS)
        for job, check in state.items():
            account = check["account"]
            assert account in credentials, f"{job} has no credentials of its own"
            expected = "one" if "one" in job else "two"
            assert expected in credentials[account]["query_url"]
