# Use an official Python runtime as a base image
FROM ubuntu:xenial

## The maintainer name and email
MAINTAINER Rick Nitsche <rick@phas.ubc.ca>

RUN set -xe

# Install any needed packages specified in requirements.txt
RUN apt-get update
RUN apt-get install -y software-properties-common
RUN add-apt-repository ppa:jonathonf/python-3.6
RUN apt-get update
RUN apt-get install -y python3.6 python3.6-dev
RUN apt-get install -y git
RUN apt-get install -y curl
RUN apt-get install -y build-essential  # autoconf libtool pkg-config
RUN curl https://bootstrap.pypa.io/get-pip.py | python3.6

RUN git clone https://github.com/chime-experiment/comet.git
RUN pip install -r /comet/requirements.txt
RUN pip install /comet

# Minimize container size
RUN apt-get remove -y curl git
RUN apt-get autoremove -y
RUN apt-get clean -y
RUN rm -rf /tmp/build

# Run comet when the container launches
CMD comet --debug 1 --recover 0
