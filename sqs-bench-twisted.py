#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from pprint import pformat
from sortedcontainers import SortedList
from sys import argv
from time import sleep
from twisted.internet import reactor, task
from twisted.internet import stdio
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import Protocol
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.task import react
from twisted.protocols import basic
from twisted.web.client import Agent, HTTPConnectionPool, readBody
from twisted.web.http_headers import Headers
import argparse
import boto3
import datetime
import math
import time
import uuid

# QUEUE_URL = 'https://sqs.eu-west-1.amazonaws.com/903900208897/sqs-benchmark'
QUEUE_URL = 'https://sqs.eu-west-1.amazonaws.com/245915766340/sqs-benchmark-2'

sqs = boto3.client('sqs')
# ENDPOINT = 'http://lbkt-sas-010.stat.yandex.net:8771'
# sqs = boto3.client('sqs',region_name='yandex',endpoint_url=ENDPOINT)


def percentile(N, percent):
    """
    Find the percentile of a list of values.

    @parameter N - is a list of values. Note N MUST BE already sorted.
    @parameter percent - a float value from 0.0 to 1.0.

    @return - the percentile of the values
    """
    if not N:
        return None
    k = (len(N)-1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return N[int(k)]
    d0 = N[int(f)] * (c-k)
    d1 = N[int(c)] * (k-f)
    return d0+d1

class WebClientContextFactory(ClientContextFactory):
    def getContext(self, hostname, port):
        return ClientContextFactory.getContext(self)

class IgnoreBody(Protocol):
    def __init__(self, deferred):
        self.deferred = deferred

    def dataReceived(self, bytes):
        pass

    def connectionLost(self, reason):
        self.deferred.callback(None)

# pool = HTTPConnectionPool(reactor, persistent=True)
# pool.maxPersistentPerHost = 5

class Requestor:
  def __init__(self, queueUrl, maxInflight, stopAt, bodySize, warmupTime):
    self.queueUrl = queueUrl
    self.inflight = 0
    self.maxInflight = maxInflight
    self.startedAt = datetime.datetime.now()
    self.stopAt = stopAt
    self.bodySize = bodySize
    self.body = "x" * bodySize
    self.lastRequestMadeAt = None
    self.warmupTime = float(warmupTime)

    self.warmedUp = False
    self.requests = {}
    self.requestsDone = []
    self.requestsNum = 0
    self.requestsTimes = SortedList()
    self.errorsNum = 0
    self.timedoutNum = 0

    self.startPeriodicTask(self.printStats, 1.0)
    self.startPeriodicTask(self.cancelLongRequests, 1.0)

  def startPeriodicTask(task, period):
    t = task.LoopingCall(task)
    d = t.start(period)
    d.addErrback(self.cbErr)

  def cancelLongRequests():
    for req in self.requests:

    pass

  def requestGet(self, url=None):
      self.inflight += 1
      params = {
        'QueueUrl': self.queueUrl,
        'MessageBody': self.body
      }
      if url is None:
        url = sqs.generate_presigned_url('send_message', Params=params, ExpiresIn=3600, HttpMethod="GET").encode('latin-1')
      # url = "http://httpbin.org/ip"
      now = datetime.datetime.now()
      self.lastRequestMadeAt = now
      reqId = uuid.uuid4()
      self.requests[reqId] = { 'startedAt': now }
      d = agent.request('GET', url)
      d.addCallback(self.cbRequest, reqId)
      # d.addCallback(cbShutdown)
      d.addErrback(self.cbRequestErr, reqId)
      d.addBoth(self.cbComplete, reqId)
      timeoutCall = reactor.callLater(5, self.dropRequest, d, reqId)
      self.requests[reqId]['timeoutCall'] = timeoutCall
      return d

  def printStats(self):
    elapsedTime = datetime.datetime.now() - self.startedAt
    rps = self.requestsNum / elapsedTime.total_seconds()
    timedoutRate = 0.0
    if self.requestsNum > 0:
      timedoutRate = self.timedoutNum / self.requestsNum
    print("Inflight %s, RPS: %2.f, requests made %s, timed out %s (%.3f%%), errors num %s, elapsed time %s" % (self.inflight, rps, self.requestsNum, self.timedoutNum, timedoutRate, self.errorsNum, elapsedTime))
    if self.requestsNum > 0:
      pcs = {
        '1': percentile(self.requestsTimes, 1),
        '0.99': percentile(self.requestsTimes, 0.99),
        '0.95': percentile(self.requestsTimes, 0.95),
        '0.90': percentile(self.requestsTimes, 0.90),
        '0.5': percentile(self.requestsTimes, 0.5),
        '0.01': percentile(self.requestsTimes, 0.01),
      }
      print("Request time percentiles - 100%%: %.3f, 0.99%%: %.3f, 0.95%%: %.3f, 0.90%%: %0.3f, 0.5%%: %.3f, 0.01%%: %.3f" % (pcs['1'], pcs['0.99'], pcs['0.95'], pcs['0.90'], pcs['0.5'], pcs['0.01']))
    # print("Last request was made at %s" % (self.lastRequestMadeAt))

  def dropRequest(self, d, reqId):
    self.timedoutNum += 1
    d.cancel()
    self.ensureInflight()

  def ensureInflight(self):
    now = datetime.datetime.now()

    effectiveMaxInflight = self.maxInflight
    if not self.warmedUp:
      elapsedTime = (now - self.startedAt).total_seconds()
      if elapsedTime >= self.warmupTime:
        self.warmedUp = True
      else:
        effectiveMaxInflight = max(1, int(self.maxInflight * (elapsedTime / self.warmupTime)))

    # print("effective max inflight: %s, inflight: %s" % (effectiveMaxInflight, self.inflight))

    if now < self.stopAt:
      for i in range(effectiveMaxInflight - self.inflight):
        self.requestGet()
    elif self.inflight == 0:
      self.stop()
    # print("effective max inflight: %s, inflight: %s" % (effectiveMaxInflight, self.inflight))

  def cbComplete(self, ignored, reqId):
    self.requests[reqId]['finishedAt'] = datetime.datetime.now()
    self.requestsDone.append(dict(self.requests[reqId]))
    if self.requests[reqId]['timeoutCall'].active():
      self.requests[reqId]['timeoutCall'].cancel()

  def cbRequest(self, response, reqId):
      # print 'Response version:', response.version
      # print 'Response code:', response.code
      # print 'Response phrase:', response.phrase
      # print 'Response headers:'
      # print pformat(list(response.headers.getAllRawHeaders()))
      d = readBody(response)
      d.addCallback(self.cbBody, reqId)
      return d

      # print 'Response code:', response.code
      # finished = Deferred()
      # response.deliverBody(IgnoreBody(finished))
      # return finished

  def cbBody(self, body, reqId):
      # print('.', end='')
      # print('Response body:' + body)
      self.inflight -= 1
      self.requestsNum += 1
      # print(datetime.datetime.now(), self.stopAt)
      now = datetime.datetime.now()
      requestElapsedTime = now - self.requests[reqId]['startedAt']
      self.requestsTimes.add(requestElapsedTime.total_seconds())
      self.ensureInflight()

  def stop(self):
    # stoppedAt = datetime.datetime.now()
    # elapsedTime = stoppedAt - self.startedAt
    # rps = self.requestsNum / elapsedTime.total_seconds()
    # print("Started at %s, scheduled to run until %s, stopped at %s, elapsed time %s" % (self.startedAt, self.stopAt, stoppedAt, str(elapsedTime)))
    # print("RPS is %.2f" % rps)
    # print("Requests num %s, errors num %s" % (self.requestsNum, self.errorsNum))
    self.printStats()
    # for req in self.requestsDone:
      # print("%s %s" % (req['startedAt'].isoformat(), req['finishedAt'].isoformat()))
    reactor.stop()

  def cbRequestErr(self, err, reqId):
    self.inflight -= 1
    if not err.check(twisted.web._newclient.ResponseNeverReceived):
      self.errorsNum += 1
      print(err)
    self.ensureInflight()

  def cbErr(self, err):
    print(err)

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("--duration", "-d", type=int, default=10, help="Run duration, sec")
parser.add_argument("--body-size", "-s", type=int, default=10, help="Message body size, bytes")
parser.add_argument("--max-inflight", "-i", type=int, default=10, help="Max inflight")
parser.add_argument("--warmup", "-w", type=int, default=10, help="Warmup period, sec")
parser.add_argument("--timeout", "-t", type=int, default=5, help="Timeout, sec")
args = parser.parse_args()

# d = requestGet("http://httpbin.org/ip").addCallback(
    # lambda ign: requestGet("http://httpbin.org/ip"))
pool = HTTPConnectionPool(reactor, persistent=True)
pool.maxPersistentPerHost = 100
contextFactory = WebClientContextFactory()
agent = Agent(reactor, contextFactory, pool=pool)

def wait_for_sec_start():
    start_sec = int(time.time())
    sec = start_sec
    while sec == start_sec:
      sleep(0.010)
      sec = int(time.time())

wait_for_sec_start()

stopAt = (datetime.datetime.now() + datetime.timedelta(seconds=args.duration)).replace(microsecond=0)
r = Requestor(QUEUE_URL, args.max_inflight, stopAt, args.body_size, args.warmup)
r.ensureInflight()

# reactor.suggestThreadPoolSize(30)
reactor.run()
