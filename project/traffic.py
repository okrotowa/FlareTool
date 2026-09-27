"""Burst traffic for the demo Lambdas, so metrics react quickly.

Usage:
    python project/traffic.py                 # 50 calls per function
    python project/traffic.py --count 200
    python project/traffic.py --only checkout

Requires: pip install boto3, and AWS credentials allowed to invoke the functions.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import boto3

FUNCTIONS = ["tfpulse-demo-catalog", "tfpulse-demo-orders", "tfpulse-demo-checkout"]


def invoke(client, name):
    resp = client.invoke(FunctionName=name, InvocationType="RequestResponse")
    return name, "error" if resp.get("FunctionError") else "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--only", help="catalog, orders or checkout")
    parser.add_argument("--region", default="eu-central-1")
    args = parser.parse_args()

    names = [f for f in FUNCTIONS if not args.only or f.endswith(args.only)]
    client = boto3.client("lambda", region_name=args.region)
    calls = [n for n in names for _ in range(args.count)]

    results = Counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        for name, status in pool.map(lambda n: invoke(client, n), calls):
            results[(name, status)] += 1

    for name in names:
        ok, err = results[(name, "ok")], results[(name, "error")]
        print(f"{name:28} ok={ok:4}  errors={err:4}")


if __name__ == "__main__":
    main()
