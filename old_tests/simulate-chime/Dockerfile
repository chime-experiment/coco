# Use an official Python runtime as a base image
FROM ubuntu:xenial

## The maintainer name and email
MAINTAINER Rick Nitsche <rick@phas.ubc.ca>

RUN set -xe

# Install any needed packages specified in requirements.txt
RUN apt-get update
RUN apt-get install -y gcc
RUN apt-get install -y cmake
RUN apt-get install -y libhdf5-10 libhdf5-10-dbg libhdf5-dev h5utils
RUN apt-get install -y libboost-all-dev
RUN apt-get install -y python python-setuptools python-pip
RUN apt-get install -y libevent-dev
RUN apt-get install -y git
RUN apt-get install -y libssl-dev
RUN pip install pyyaml
RUN pip install yamllint

# Minimize container size
RUN apt-get autoremove -y
RUN apt-get clean -y
RUN cd /
RUN rm -rf /tmp/build

# Build kotekan
RUN mkdir -p /code
COPY ./kotekan /code/kotekan
COPY ./highfive /code/highfive
RUN cd /code/kotekan/build && cmake -DUSE_HDF5=ON -DHIGHFIVE_PATH=$PWD/../../highfive ..
RUN cd /code/kotekan/build && make -j 4

# Run kotekan when the container launches
WORKDIR /code/kotekan/build/kotekan/
CMD ./kotekan -o