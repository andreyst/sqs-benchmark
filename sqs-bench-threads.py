#!/usr/bin/python
# -*- coding: utf-8 -*-
import requests
import boto3
import time
from time import sleep
from multiprocessing import Pool, TimeoutError
import os
import sys
import datetime

def wait_for_sec_start():
    start_sec = int(time.time())
    sec = start_sec
    while sec == start_sec:
      sleep(0.010)
      sec = int(time.time())

def send(params):
    (target_secs, body_size) = params

    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.eu-west-1.amazonaws.com/245915766340/sqs-benchmark-2'
    message_body = "x" * body_size

    wait_for_sec_start()

    requests_performed = 0
    start_time = time.time()
    started_at = datetime.datetime.now().isoformat()
    elapsed_time = 0.0

    while True:
      # params = {
        # 'QueueUrl': queue_url,
        # 'MessageBody': message_body
      # }
      # url = generate_presigned_url('ReceiveMessage', Params=params, ExpiresIn=3600, HttpMethod="POST")
      # Content-Type application/x-www-form-urlencoded

      sqs.send_message(QueueUrl = queue_url, MessageBody = message_body)

      res = sqs.receive_message(QueueUrl = queue_url)
      if not 'Messages' in res:
        continue

      receipt_handles = [ {'Id': str(idx), 'ReceiptHandle': msg['ReceiptHandle']} for idx, msg in enumerate(res['Messages']) ]
      sqs.delete_message_batch(QueueUrl = queue_url, Entries = receipt_handles)

      requests_performed += 1

      elapsed_time = time.time() - start_time
      if elapsed_time >= target_secs:
        break

    elapsed_time = time.time() - start_time
    return {
      'avg_rps' : round(requests_performed / elapsed_time, 2),
      'elapsed_time': round(elapsed_time, 3),
      'started_at': started_at,
      'finished_at': datetime.datetime.now().isoformat(),
    }

if __name__ == "__main__":
    start_time = datetime.datetime.now().isoformat()
    secs = 10
    processes = 1
    body_size = 10
    if len(sys.argv) > 1:
      secs = int(sys.argv[1])
    if len(sys.argv) > 2:
      processes = int(sys.argv[2])
    if len(sys.argv) > 3:
      body_size = int(sys.argv[3])

    print "Started at " + datetime.datetime.now().isoformat()
    pool = Pool(processes=processes)
    print "Created pool at " + datetime.datetime.now().isoformat()

    results = pool.map(send, [[secs, body_size]] * processes)
    print "Got map at " + datetime.datetime.now().isoformat()
    for res in results: print res
    # print [ res['avg'] for res in results ]
    total_rps = 0
    for res in results:
      total_rps += res['avg_rps']

    print "Started at %s, ended at %s, rps: %s" % (start_time, datetime.datetime.now().isoformat(), total_rps)
