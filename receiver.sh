#!/usr/bin/env bash
/usr/bin/storescp --promiscuous -od "/home/hermes/DCMAnonymize/incoming" -ss study -tos 60 +uf -xcs "/home/hermes/DCMAnonymize/anonymize.py #p" 5001
