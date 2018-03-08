import boto3

sqs = boto3.client('sqs')
QUEUE_URL = 'https://sqs.eu-west-1.amazonaws.com/245915766340/sqs-benchmark-2'
BODY = 'x' * 10
params = {'QueueUrl':QUEUE_URL,'MessageBody':BODY}

header = """
[Host: eu-west-1.queue.amazonaws.com]
[Connection: close]
[User-Agent: Tank]
"""
print(header.strip())

for i in range(1, 100):
  print(sqs.generate_presigned_url('send_message', Params=params, ExpiresIn=3600, HttpMethod="GET").replace("https://eu-west-1.queue.amazonaws.com", ""))

