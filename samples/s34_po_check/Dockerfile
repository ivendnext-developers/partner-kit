# S34's service as a container on your own server, serving many shops (CitiXsys hosting runs it as a function: app.json)
# (the app template's handshake). Built from the KIT'S ROOT, because it uses the template's handshake, never a copy of it:
#   docker build --platform linux/arm64 -f samples/s34_po_check/Dockerfile -t po-check:0.1.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s34_po_check/po_check.py samples/s34_po_check/erp.py samples/s34_po_check/erp_standin.json /app/samples/s34_po_check/
COPY samples/s34_po_check/service/app.py /app/samples/s34_po_check/service/app.py

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each shop hands over its own at connect. IVN_LIBRARY_APP and POC_PREFIX come from the platform's
# settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting. Your ERP's address and key go there too, in place of the stand-in.
CMD ["python3", "samples/s34_po_check/service/app.py"]
