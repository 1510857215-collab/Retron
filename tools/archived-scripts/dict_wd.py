# -*- coding: utf-8 -*-
"""Wikidata 查询小工具（走代理）。"""
import json, urllib.request, urllib.parse

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
_opener = urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))
UA = "hx-local-chemdict/2.0 (contact: local offline toolkit)"

def sparql(q, timeout=180):
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": q, "format": "json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json",
                                               "User-Agent": UA})
    with _opener.open(req, timeout=timeout) as f:
        return json.loads(f.read().decode("utf-8"))

if __name__ == "__main__":
    import sys
    q = """SELECT (COUNT(DISTINCT ?item) AS ?c) WHERE {
      ?item wdt:P662 ?cid .
      ?item rdfs:label ?l . FILTER(lang(?l)="zh")
    }"""
    r = sparql(q)
    print("zh-labeled items with P662:", r["results"]["bindings"])
