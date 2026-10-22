FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential ca-certificates git cmake curl python3 libtool libboost-all-dev \
    default-libmysqlclient-dev libssl-dev libreadline-dev zlib1g-dev libbz2-dev \
    libncurses5-dev liblzma-dev && rm -rf /var/lib/apt/lists/*

# Source pins, patches, configuration and compilation belong to tools/build_realm.py.
