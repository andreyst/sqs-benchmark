#!/bin/bash

echo "[sqs-benchmark]" > hosts
aws ec2 describe-instances --filter Name=tag:Purpose,Values=SqsBenchmark --filter Name=instance-state-name,Values=running --query 'Reservations[*].Instances[*].PublicIpAddress' --output json | python -c "import sys;import json; buf = sys.stdin.read(); data = json.loads(buf); print '\n'.join([ ip for ip_list in data for ip in ip_list ])" >> hosts
echo -n "New inventory size: "
grep -v "sqs-benchmark" hosts | wc -l
