#!/bin/bash
IMAGE="guruevi/dcmanonymizer"
VERSION="0.8"
docker build . -t ${IMAGE}:${VERSION} --platform linux/amd64
docker tag ${IMAGE}:${VERSION} ${IMAGE}:latest
docker push ${IMAGE}:latest
