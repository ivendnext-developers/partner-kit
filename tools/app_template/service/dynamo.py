"""The shops table on CitiXsys hosting: one DynamoDB table per app, reached with the standard library only.

The hosting module (`modules/app`, `shops = true`) makes the table, encrypted at rest with the account's key, and a
role only this app's containers take, allowed to read and write that table and nothing else. This file signs each
request with AWS Signature Version 4 (the documented algorithm, docs.aws.amazon.com "Create a signed AWS API request")
using the container's own temporary credentials (the ECS credentials address), or the AWS_* variables on a laptop.

Each shop is one item: ``site`` (the key) and ``record`` (the shop's JSON). Nothing is printed or logged here.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request

TARGET = "DynamoDB_20120810."
_ECS = "http://169.254.170.2"


class StoreError(Exception):
    """The table did not answer as it should (no secret, no body in the message)."""


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign(method: str, host: str, path: str, region: str, service: str, headers: dict, body: bytes,
         creds: dict, now: datetime.datetime) -> dict:
    """The headers to send: ``headers`` plus host, x-amz-date, the session token and Authorization (SigV4)."""
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    h = {k.lower(): v.strip() for k, v in headers.items()}
    h.update({"host": host, "x-amz-date": amz})
    if creds.get("token"):
        h["x-amz-security-token"] = creds["token"]
    names = sorted(h)
    canonical = "\n".join([method, path, "", "".join(f"{k}:{h[k]}\n" for k in names), ";".join(names),
                           hashlib.sha256(body).hexdigest()])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + creds["secret"]).encode(), day), region), service), "aws4_request")
    h["authorization"] = (f"AWS4-HMAC-SHA256 Credential={creds['key']}/{scope}, SignedHeaders={';'.join(names)}, "
                          f"Signature={hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()}")
    return h


class Credentials:
    """The container's temporary credentials, fetched again five minutes before they end."""

    def __init__(self, env=os.environ):
        self.env, self._c, self._until, self._lock = env, None, 0.0, threading.Lock()

    def get(self) -> dict:
        with self._lock:
            if self._c and time.time() < self._until:
                return self._c
            rel, full = self.env.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"), self.env.get("AWS_CONTAINER_CREDENTIALS_FULL_URI")
            if rel or full:
                req = urllib.request.Request(_ECS + rel if rel else full)
                if self.env.get("AWS_CONTAINER_AUTHORIZATION_TOKEN"):
                    req.add_header("Authorization", self.env["AWS_CONTAINER_AUTHORIZATION_TOKEN"])
                with urllib.request.urlopen(req, timeout=3) as r:
                    d = json.loads(r.read())
                self._c = {"key": d["AccessKeyId"], "secret": d["SecretAccessKey"], "token": d.get("Token")}
                ends = datetime.datetime.strptime(d["Expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                self._until = ends.timestamp() - 300
            elif self.env.get("AWS_ACCESS_KEY_ID"):
                self._c = {"key": self.env["AWS_ACCESS_KEY_ID"], "secret": self.env["AWS_SECRET_ACCESS_KEY"],
                           "token": self.env.get("AWS_SESSION_TOKEN")}
                self._until = time.time() + 300
            else:
                raise StoreError("no AWS credentials: the shops table is reachable only on CitiXsys hosting")
            return self._c


class TableStore:
    """``get``, ``put``, ``delete`` and ``sites`` over the app's own table (the FileStore's interface)."""

    def __init__(self, table: str, region: str | None, creds: Credentials | None = None, endpoint: str | None = None):
        if not region:
            raise SystemExit("IVN_SHOPS_TABLE is set but AWS_REGION is not")
        self.table, self.region = table, region
        self.host = endpoint or f"dynamodb.{region}.amazonaws.com"
        self.creds = creds or Credentials()

    def _call(self, op: str, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        headers = sign("POST", self.host, "/", self.region, "dynamodb",
                       {"content-type": "application/x-amz-json-1.0", "x-amz-target": TARGET + op}, body,
                       self.creds.get(), datetime.datetime.now(datetime.timezone.utc))
        req = urllib.request.Request(f"https://{self.host}/", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            with e:
                try:
                    kind = (json.loads(e.read() or b"{}").get("__type") or "").rsplit("#", 1)[-1]
                except (ValueError, AttributeError):
                    kind = "?"
            raise StoreError(f"{op} answered {e.code} {kind}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise StoreError(f"{op} unreachable ({type(e).__name__})") from None

    def get(self, site: str) -> dict | None:
        item = self._call("GetItem", {"TableName": self.table, "Key": {"site": {"S": site}},
                                      "ConsistentRead": True}).get("Item")
        return json.loads(item["record"]["S"]) if item else None

    def put(self, site: str, record: dict):
        self._call("PutItem", {"TableName": self.table,
                               "Item": {"site": {"S": site}, "record": {"S": json.dumps(record)}}})

    def delete(self, site: str):
        self._call("DeleteItem", {"TableName": self.table, "Key": {"site": {"S": site}}})

    def sites(self) -> list[str]:
        out, start = [], None
        while True:
            q = {"TableName": self.table, "ProjectionExpression": "site", "ConsistentRead": True}
            if start:
                q["ExclusiveStartKey"] = start
            page = self._call("Scan", q)
            out += [i["site"]["S"] for i in page.get("Items", []) if "|" not in i["site"]["S"]]   # never a claim
            start = page.get("LastEvaluatedKey")
            if not start:
                return sorted(out)

    def claim(self, name: str, now: float, stale_s: float) -> bool:
        """Take ``name`` (a claim's name holds a "|", which no site's does) unless another call took it less than
        ``stale_s`` seconds ago: one conditional write, so of two copies of the app racing for it exactly one wins. The
        caller deletes it when done; a copy stopped before that leaves it, and it is taken over once stale. A caller may
        pass an EXPIRY as ``now`` (``function.Claimed``: its time + ``stale_s``), and the claim is then taken over once
        that expiry has passed; one name is always claimed one way."""
        try:
            self._call("PutItem", {"TableName": self.table, "Item": {"site": {"S": name}, "at": {"N": str(now)}},
                                   "ConditionExpression": "attribute_not_exists(site) OR #at <= :stale",
                                   "ExpressionAttributeNames": {"#at": "at"},
                                   "ExpressionAttributeValues": {":stale": {"N": str(now - stale_s)}}})
        except StoreError as e:
            if str(e).endswith(" ConditionalCheckFailedException"):
                return False
            raise
        return True
