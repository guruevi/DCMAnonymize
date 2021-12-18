#!/bin/bash
IMAGE="guruevi/dcmanonymizer"
VERSION="0.5"
docker build . -t ${IMAGE}:${VERSION}
docker tag ${IMAGE}:${VERSION} ${IMAGE}:latest
# docker push ${IMAGE}:latest
