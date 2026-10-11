# بات «رشد» برای پلتفرم‌های کانتینری (مثل دارکوب هم‌روش)
# اگر دریافت ایمیج پایه از Docker Hub روی پلتفرم خطا داد، خط اول را با یک رجیستری آینه‌ای عوض کنید
# (مثلاً از رجیستری آروان؛ نشانی دقیق را از مستندات خودشان بگیرید).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    PANEL_HOST=0.0.0.0 \
    PANEL_PORT=8090

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY assets ./assets

# پوشه‌ی داده؛ دیسک دائمی پلتفرم باید روی /data وصل شود
RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8090

CMD ["python", "-m", "app.main"]
