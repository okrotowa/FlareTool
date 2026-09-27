import random
import time


def handler(event, context):
    # Simulates a slow payment provider call: 0.8-1.5 s.
    # Fine with timeout = 10; mostly times out with timeout = 1.
    time.sleep(random.uniform(0.8, 1.5))
    return {"statusCode": 200, "body": "order placed"}
