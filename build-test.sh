#!/bin/bash
IMAGE="guruevi/dcmanonymizer"
docker rm dcmanonymizer_test
rm -rf test-data/out/*
cp config/* myconfig/
docker run --mount type=bind,source="$(pwd)"/test-data/in,target=/in \
           --mount type=bind,source="$(pwd)"/test-data/out,target=/out \
           --mount type=bind,source="$(pwd)"/myconfig,target=/app/config \
           --name dcmanonymizer_test \
           -d ${IMAGE}
sleep 5
docker logs dcmanonymizer_test