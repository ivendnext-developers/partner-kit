# S52's service as a container on your own server, serving many retailers (CitiXsys hosting runs it as a function: app.json),
# with the app template's handshake. Built from the KIT'S ROOT, because it uses the template's handshake and the kit's feed
# client, never a copy of them:
#   docker build --platform linux/arm64 -f samples/s52_phone_plans/Dockerfile -t phone-plans:0.1.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY tools/feed_client/feed_client.py /app/tools/feed_client/feed_client.py
COPY samples/s52_phone_plans/service/ /app/samples/s52_phone_plans/service/

USER app
ENV PORT=8080 PP_STATE=/home/app/state
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each retailer hands over its own at connect, and keeps its telecom account in its own settings record.
# IVN_LIBRARY_APP, TEL_PREFIX and TEL_API come from the platform's settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting.
CMD ["python3", "samples/s52_phone_plans/service/app.py"]
