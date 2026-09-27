import random
import time


def handler(event, context):
    time.sleep(random.uniform(0.05, 0.15))
    return {"statusCode": 200, "body": "catalog ok"}
