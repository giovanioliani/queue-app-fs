#!/bin/bash

IP="10.0.10.141"
password="tijolo22"
sshpass -p $password scp client.py server.py  root@$IP:~/queueapp/queue-app-fs
