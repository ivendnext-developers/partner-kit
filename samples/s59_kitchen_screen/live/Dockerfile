# S59's live service, a container beside the service (CitiXsys hosting runs the service itself as a function: ../app.json).
# Built from the KIT'S ROOT, because it uses the service's own admission check and the template's table reader, never
# a copy of them:
#   docker build --platform linux/arm64 -f samples/s59_kitchen_screen/live/Dockerfile -t kitchen-screen-live:1.1.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s59_kitchen_screen/ksc.py /app/samples/s59_kitchen_screen/ksc.py
COPY samples/s59_kitchen_screen/service/app.py /app/samples/s59_kitchen_screen/service/app.py
COPY samples/s59_kitchen_screen/live/live.py samples/s59_kitchen_screen/live/sitesocket.py /app/samples/s59_kitchen_screen/live/

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: it reads each retailer's key from the service's own table, which the hosting lets it read and nothing else.
CMD ["python3", "samples/s59_kitchen_screen/live/live.py"]
