# Local Globus Compute endpoint. Register the function using the same Python
# version (3.11) and a matching globus-compute-sdk version.
FROM python:3.11-slim

RUN pip install --no-cache-dir globus-compute-endpoint

# Run as a non-root user: as root, the endpoint is configured as a
# multi-user endpoint, which is not what we want here.
RUN useradd --create-home --uid 1000 compute \
 && mkdir -p /home/compute/.globus_compute \
 && chown -R compute:compute /home/compute
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
USER compute
ENV HOME=/home/compute

ENV ENDPOINT_NAME=powerball-local
ENTRYPOINT ["/entrypoint.sh"]
