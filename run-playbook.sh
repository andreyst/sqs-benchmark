#!/bin/bash

ansible-playbook sqs-benchmark.yml -i hosts --key-file "~/.ssh/krz-2017.pem" -u ubuntu
