# S25's service on a server, serving many shops (the app template's handshake). Built from the KIT'S ROOT, because it
# uses the template's handshake and the feed client, never copies of them (S22's Dockerfile, the same shape):
#   docker build --platform linux/arm64 -f samples/s25_gift_on_spend/Dockerfile -t gift-card-on-spend:1.1.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY tools/feed_client/feed_client.py /app/tools/feed_client/feed_client.py
COPY samples/s25_gift_on_spend/service/ /app/samples/s25_gift_on_spend/service/

# CitiXsys hosting mounts an empty, writable /scratch here when the app asks for one (`scratch = true`): the folder made
# below, owned by the app, is what lets a non-root user write in it (an empty volume is otherwise root's, mode 0755).
# PP_STATE points inside it.
RUN mkdir /scratch && chown app:app /scratch
VOLUME ["/scratch"]

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails (503 once the feed worker has stalled for three minutes).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each shop's site hands over the key of the app's own user at connect. IVN_LIBRARY_APP, GCS_PREFIX and
# PP_STATE come from the platform's settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting.
CMD ["python3", "samples/s25_gift_on_spend/service/app.py"]
