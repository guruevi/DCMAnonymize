#!/bin/bash
docker rm dcmanonymizer_test
rm -rf test-data/out/*
cp config/* myconfig/
docker run --mount type=bind,source="$(pwd)"/test-data/in,target=/in \
           --mount type=bind,source="$(pwd)"/test-data/out,target=/out \
           --mount type=bind,source="$(pwd)"/test-data/reports,target=/reports \
           --mount type=bind,source="$(pwd)"/test-data/original,target=/data \
           --mount type=bind,source="$(pwd)"/myconfig,target=/app/config \
           --name dcmanonymizer_test \
           --network sorter-net \
           -d guruevi/dcmanonymizer
docker logs dcmanonymizer_test