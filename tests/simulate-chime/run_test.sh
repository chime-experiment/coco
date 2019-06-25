#!/bin/bash

# Build kotekan and dependencies
if cd highfive; then git pull && cd ..; else git clone --single-branch --branch extensible-datasets https://github.com/jrs65/highfive.git; fi
if cd kotekan; then git pull; else git clone --single-branch --branch rn/stdout https://github.com/kotekan/kotekan.git && cd kotekan; fi
git status
if cd build; then cd ..; else mkdir build; fi
cd build && cmake -DUSE_HDF5=ON -DHIGHFIVE_PATH=$PWD/../../highfive ..
ls $PWD/../..
make -j 4
cd ../..

export DOCKER_CLIENT_TIMEOUT=120
export COMPOSE_HTTP_TIMEOUT=120
docker-compose -f docker-compose.yaml build
docker-compose -f docker-compose.yaml up --scale gpu-cn01=10 &
cd ../../scripts
sleep 10

PYTHONPATH=.. ./coco -c ../tests/simulate-chime/coco.conf &
COCO_PID=$!
sleep 10

PYTHONPATH=.. ./coco-client -r FULL -c ../tests/simulate-chime/coco.conf start

sleep 15

# Call some endpoints
PYTHONPATH=.. ./coco-client -c ../tests/simulate-chime/coco.conf status

PYTHONPATH=.. ./coco-client -c ../tests/simulate-chime/coco.conf stop
sleep 15

docker kill $(docker ps -q)
kill $COCO_PID
