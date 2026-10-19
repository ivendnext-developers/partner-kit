# S24's service on your own server, one shop or many (the app template's handshake). Built from the KIT'S ROOT, because it
# uses the template's handshake, never a copy of it:
#   docker build -f samples/s24_price_checker/Dockerfile -t price-checker:1.0.0 .
# On CitiXsys hosting it runs as a function instead (app.json "runs": "function"); this image is for your own host.
FROM python:3.12-slim

# Never root: the app needs no rights.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY tools/app_template/service/ /app/tools/app_template/service/
COPY samples/s24_price_checker/price.py /app/samples/s24_price_checker/price.py
COPY samples/s24_price_checker/service/app.py samples/s24_price_checker/service/kiosk.html \
     samples/s24_price_checker/service/kiosk.js samples/s24_price_checker/service/kiosk.css \
     /app/samples/s24_price_checker/service/

USER app
ENV PORT=8080
EXPOSE 8080

# The platform restarts the container when this fails.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"

# No secret here: one shop's key comes from your host's secret store (IVN_SHOP_URL, IVN_SHOP_KEY), or each shop hands
# over its own at connect (IVN_LIBRARY_APP with IVN_SHOPS_FILE).
CMD ["python3", "samples/s24_price_checker/service/app.py"]
