import random
import time


def handler(event, context):
    time.sleep(random.uniform(0.05, 0.2))
    if random.random() < 0.005:
        raise RuntimeError("Order store temporarily unavailable")
    return {"statusCode": 200, "body": "orders ok"}
