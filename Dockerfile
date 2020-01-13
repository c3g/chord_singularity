FROM debian:buster-slim

# Author: David Lougheed <david.lougheed@mail.mcgill.ca>

ENV CHORD_DOCKER_BUILD 1
ENV PYTHONUNBUFFERED 1

RUN mkdir /chord/
WORKDIR /chord/

ADD chord_services.json /chord/chord_services.json
ADD chord_services.schema.json /chord/chord_services.schema.json
ADD container_scripts /chord/container_scripts
ADD chord_container_tools /chord/chord_container_tools
ADD LICENSE /chord/LICENSE
ADD README.md /chord/README.md

RUN bash /chord/container_scripts/post_script.bash

CMD ["/bin/bash", "/chord/container_scripts/start_script.bash"]
