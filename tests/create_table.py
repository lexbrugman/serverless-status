#!/usr/bin/env python3
"""Create the history table in DynamoDB Local — run inside the Lambda base
image by dev-stack.sh, so the host needs no AWS tooling at all."""

import os

import boto3


def main() -> None:
    dynamodb = boto3.client("dynamodb", endpoint_url=os.environ["DDB_ENDPOINT"])
    name = os.environ.get("TABLE_NAME", "status-page")
    existing = dynamodb.list_tables()["TableNames"]
    if name in existing:
        print(f"table {name} already exists")
        return
    dynamodb.create_table(
        TableName=name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"created table {name}")


if __name__ == "__main__":
    main()
