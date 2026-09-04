FROM mitmproxy/mitmproxy:11

COPY log_prompts.py /scripts/log_prompts.py
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
