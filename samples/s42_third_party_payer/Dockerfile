# S42's service as a container on your own server, serving many shops (CitiXsys hosting runs it as a function: app.json)
# (the app template's handshake). Built from the KIT'S ROOT, because it uses the template's handshake, never a copy:
#   docker build --platform linux/arm64 -f samples/s42_third_party_payer/Dockerfile -t third-party-payer:0.1.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s42_third_party_payer/copay.py samples/s42_third_party_payer/claims.py /app/samples/s42_third_party_payer/
COPY samples/s42_third_party_payer/service/app.py /app/samples/s42_third_party_payer/service/app.py

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each shop hands over its own at connect. IVN_LIBRARY_APP and ICP_PREFIX come from the platform's
# settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting. Members and claims are health data for a pharmacy: run it
# in the shop's own region.
CMD ["python3", "samples/s42_third_party_payer/service/app.py"]
