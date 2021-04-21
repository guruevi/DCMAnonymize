#!/bin/bash
IMAGE="guruevi/dcmanonymizer"
VERSION="0.4"
docker build . -t ${IMAGE}:${VERSION}
docker tag ${IMAGE}:${VERSION} ${IMAGE}:latest
