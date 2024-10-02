FROM ubuntu:22.04

WORKDIR /home
COPY . .

RUN apt update \
&& apt upgrade -y \
&& apt install -y libopenmpi-dev python3 python3-pip \
&& rm -rf /var/lib/apt/lists/* \
&& pip install -r requirements.txt

CMD ["tail", "-f", "/dev/null"]

