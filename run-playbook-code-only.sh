#!/bin/bash

ansible-playbook sqs-benchmark.yml -i hosts --key-file "~/.ssh/krz-2017.pem" -u ubuntu --tags code

# ansible all -a "python sqs-bench.py 30 8" -i hosts --key-file "~/.ssh/krz-2017.pem" -u ubuntu | grep -v "SUCCESS"