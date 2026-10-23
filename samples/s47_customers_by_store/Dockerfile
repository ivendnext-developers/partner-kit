# S47's service as a container on your own server, serving many shops (CitiXsys hosting runs it as a function: app.json) (the app template's handshake). Built from the KIT'S ROOT, because it
# uses the template's handshake, never a copy of it:
#   docker build --platform linux/arm64 -f samples/s47_customers_by_store/Dockerfile -t customers-by-store:1.0.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s47_customers_by_store/storerules.py /app/samples/s47_customers_by_store/storerules.py
COPY samples/s47_customers_by_store/service/app.py /app/samples/s47_customers_by_store/service/app.py

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each shop hands over its own at connect. IVN_LIBRARY_APP and CBS_PREFIX come from the platform's
# settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting.
CMD ["python3", "samples/s47_customers_by_store/service/app.py"]
