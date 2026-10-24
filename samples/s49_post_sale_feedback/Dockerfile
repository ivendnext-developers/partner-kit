# S49's service as a container on your own server, serving many retailers (CitiXsys hosting runs it as a function:
# app.json) (the app template's handshake). Built from the KIT'S ROOT, because it uses the template's handshake, never
# a copy of it:
#   docker build --platform linux/arm64 -f samples/s49_post_sale_feedback/Dockerfile -t post-sale-feedback:1.0.0 .
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s49_post_sale_feedback/feedback.py /app/samples/s49_post_sale_feedback/feedback.py
COPY samples/s49_post_sale_feedback/service/ /app/samples/s49_post_sale_feedback/service/

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: each retailer hands over its own at connect. IVN_LIBRARY_APP, PSF_PREFIX and PSF_PAGE_URL come from
# the platform's settings; IVN_SHOPS_TABLE and AWS_REGION from the hosting.
CMD ["python3", "samples/s49_post_sale_feedback/service/app.py"]
