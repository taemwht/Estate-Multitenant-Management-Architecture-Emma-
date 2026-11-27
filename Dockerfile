FROM nousresearch/hermes-agent:latest
USER root
RUN /opt/hermes/.venv/bin/python3 -m ensurepip --upgrade && \
    /opt/hermes/.venv/bin/python3 -m pip install psycopg2-binary requests
RUN apt-get update && apt-get install -y python3-psycopg2 python3-requests && rm -rf /var/lib/apt/lists/*