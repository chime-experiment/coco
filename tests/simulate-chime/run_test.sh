#!/bin/bash

# Build kotekan and dependencies
echo "===== Checking highfive repository. ============="
if cd highfive; then git pull && cd ..; else git clone --single-branch --branch extensible-datasets https://github.com/jrs65/highfive.git; fi

echo "===== Checking kotekan repository. =============="
if cd kotekan; then git pull; else git clone --single-branch --branch rn/stdout https://github.com/kotekan/kotekan.git && cd kotekan; fi
git status
if cd build; then cd ..; else mkdir build; fi

echo "===== Building kotekan. ========================="
cd build && cmake -DUSE_HDF5=ON -DHIGHFIVE_PATH=$PWD/../../highfive ..
make -j 4
cd ../..

echo "===== Building docker images. ==================="
export DOCKER_CLIENT_TIMEOUT=120
export COMPOSE_HTTP_TIMEOUT=120
docker-compose -f docker-compose.yaml build

echo "===== Starting docker images. ==================="
docker-compose -f docker-compose.yaml up --scale gpu-cn01=10 -d
cd ../../scripts

echo "===== Waiting for docker images to start. ======="
sleep 5

echo "===== Starting coco. ============================"
PYTHONPATH=.. ./coco -c ../tests/simulate-chime/coco.conf &
COCO_PID=$!

echo "===== Waiting for coco to start. ================"
sleep 2

echo "===== Running client for tests. ================="
PYTHONPATH=.. python3.7 -m pytest -s ../tests/simulate-chime/test_client.py

echo "===== Waiting for kotekan instances to die. ====="
sleep 15

echo "===== Shutting down docker and coco. ============"
docker kill $(docker ps -q)
kill -9 $COCO_PID
