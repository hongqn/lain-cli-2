import json
from datetime import datetime, timedelta, timezone
from math import ceil
from statistics import StatisticsError, quantiles
from typing import Any, Iterable

import requests

import click
from humanfriendly import parse_timespan
from requests.exceptions import ReadTimeout

from lain_cli.utils import (
    RequestClientMixin,
    context,
    ensure_str,
    error,
    tell_cluster_config,
    warn,
)

PrometheusResult = list[dict[str, Any]]


class Prometheus(RequestClientMixin):
    timeout = 20

    def __init__(self, endpoint: str | None = None) -> None:
        if not endpoint:
            cc = tell_cluster_config()
            endpoint = cc.get("prometheus")
            if not endpoint:
                raise click.Abort(f"prometheus not provided in cluster config: {cc}")

        ctx = context(silent=True)
        self.query_range = (
            ctx.obj.get("values", {}).get("prometheus_query_range", "7d")
            if ctx
            else "7d"
        )
        self.query_step = int(int(parse_timespan(self.query_range)) / 1440)
        self.endpoint = endpoint

    @staticmethod
    def format_time(dt: str | datetime) -> str:
        if isinstance(dt, str):
            return dt
        return dt.isoformat()

    def query_cpu(
        self, appname: str, proc_name: str, **kwargs: Any
    ) -> PrometheusResult:
        cc = tell_cluster_config()
        query_template = cc.get("pql_template", {}).get("cpu")
        if not query_template:
            raise ValueError("pql_template.cpu not configured in cluster config")
        q = query_template.format(
            appname=appname, proc_name=proc_name, range=self.query_range
        )
        kwargs.setdefault("step", self.query_step)
        kwargs["end"] = datetime.now(timezone.utc)
        res = self.query(q, **kwargs)
        return res

    def cpu_p95(self, appname: str, proc_name: str, **kwargs: Any) -> tuple[int, bool]:
        accurate = True
        cpu_result = self.query_cpu(appname, proc_name)
        # [{'metric': {}, 'value': [1595486084.053, '4.990567343235413']}]
        if cpu_result:
            cpu_top_list = [ceil(float(p[-1])) for p in cpu_result[0]["values"]]
            cnt = len(cpu_top_list)
            if cpu_top_list.count(0) / cnt > 0.7:
                accurate = False

            try:
                cpu_top = int(quantiles(cpu_top_list, n=10)[-1])
            except StatisticsError:
                cpu_top = 5
        else:
            cpu_top = 5

        return max([cpu_top, 5]), accurate

    def memory_quantile(
        self, appname: str, proc_name: str, **kwargs: Any
    ) -> int | None:
        cc = tell_cluster_config()
        query_template = cc.get("pql_template", {}).get("memory_quantile")
        if not query_template:
            raise ValueError(
                "pql_template.memory_quantile not configured in cluster config"
            )
        q = query_template.format(
            appname=appname, proc_name=proc_name, range=self.query_range
        )
        kwargs.setdefault("step", self.query_step)
        res = self.query(q, **kwargs)
        if not res:
            return
        # [{'metric': {}, 'value': [1583388354.31, '744079360']}]
        memory_quantile = int(float(res[0]["value"][-1]))
        return memory_quantile

    def query(
        self,
        query: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        step: int | None = None,
        timeout: int = 20,
    ) -> PrometheusResult:
        # https://prometheus.io/docs/prometheus/latest/querying/api/#range-queries
        data = {
            "query": query,
            "timeout": timeout,
        }
        if start or end:
            start_time = start
            end_time = end or datetime.now(timezone.utc)
            if not start_time:
                if isinstance(end_time, str):
                    start_time = datetime.fromisoformat(end_time) - timedelta(days=1)
                else:
                    start_time = end_time - timedelta(days=1)

            if not step:
                step = 60

            path = "/api/v1/query_range"
            data.update(
                {
                    "start": self.format_time(start_time),
                    "end": self.format_time(end_time),
                    "step": step,
                }
            )
        else:
            path = "/api/v1/query"

        try:
            res = self.post(path, data=data)
        except ReadTimeout:
            warn("prometheus query timeout, consider using grafana instead")
            return []
        try:
            responson = res.json()
        except json.decoder.JSONDecodeError as e:
            raise ValueError(f"cannot decode: {ensure_str(res.text)}") from e
        if responson.get("status") == "error":
            err_msg = responson["error"]
            if "query timed out" in err_msg:
                warn("prometheus query timeout, consider using grafana instead")
                return []
            raise ValueError(err_msg)
        return responson["data"]["result"]


class Alertmanager(RequestClientMixin):
    """https://github.com/prometheus/alertmanager/blob/main/api/v2/openapi.yaml"""

    timeout = 20

    def __init__(self, endpoint: str | None = None) -> None:
        if not endpoint:
            cc = tell_cluster_config()
            endpoint = cc.get("alertmanager")
            if not endpoint:
                raise click.Abort(f"alertmanager not provided in cluster config: {cc}")

        self.endpoint = endpoint.rstrip("/")

    def post_alerts(
        self, labels: Iterable[tuple[str, str]] | None = None
    ) -> requests.Response | None:
        label_dic = dict(labels or (("label", "value"),))
        payload = [
            {
                "labels": label_dic,
                "annotations": label_dic,
                "generatorURL": f"{self.endpoint}/<generating_expression>",
            },
        ]
        res = self.post("/api/v2/alerts", json=payload)
        if res.status_code >= 400:
            error(res.text)
